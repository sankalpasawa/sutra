"""The seed audit against the old app's templates (work package ABS-11). Small fixture trees, never the old folder."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_old_templates.py"
spec = importlib.util.spec_from_file_location("audit_old_templates", SCRIPT)
audit_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_mod)

PRO = {"function-templates": {"identity"}, "artifact-templates": {"prd", "website"}, "engine-templates": {"generic"}}


def write(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc) if not isinstance(doc, str) else doc)


@pytest.fixture
def old(tmp_path):
    root = tmp_path / "old"
    write(root / "function-templates" / "identity" / "default.json", {"id": "identity/default", "name": "Default", "version": 1})
    write(root / "function-templates" / "identity" / "money-movement.json", {"id": "identity/money-movement", "name": "Money", "version": 1})
    write(root / "function-templates" / "audit" / "default.json", {"id": "audit/default", "name": "Default", "version": 1})
    write(root / "artifact-templates" / "prd.json", {"id": "artifact/prd", "name": "PRD", "version": 1})
    write(root / "artifact-templates" / "brief.json", {"id": "artifact/brief", "name": "Brief", "version": 1})
    write(root / "artifact-templates" / "broken.json", "{not json")
    write(root / "engine-templates" / "plan.json", {"id": "engine/plan", "name": "Plan"})
    return root


def digest(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def names(items):
    return [i["rel"] for i in items]


def test_it_says_what_pro_has_and_what_it_lacks(old):
    result = audit_mod.audit(old, PRO)
    f = result["function-templates"]
    assert names(f["has"]) == ["identity/default.json"]
    assert names(f["lacks"]) == ["audit/default.json", "identity/money-movement.json"]
    a = result["artifact-templates"]
    assert names(a["has"]) == ["prd.json"] and names(a["lacks"]) == ["brief.json", "broken.json"]
    assert names(result["engine-templates"]["lacks"]) == ["plan.json"]


def test_the_report_counts_per_kind(old):
    text = audit_mod.report(audit_mod.audit(old, PRO))
    assert "function-templates: 3 old, 1 covered by Sutra Pro, 2 lacking" in text and "  lacks   audit/default.json" in text


def test_a_dry_run_writes_nothing_anywhere(old, tmp_path, capsys):
    before = digest(old)
    assert audit_mod.main(["--old", str(old), "--dry-run", "--data-dir", str(tmp_path / "data")]) == 0
    assert digest(old) == before and not (tmp_path / "data").exists()
    assert "dry run: nothing was written" in capsys.readouterr().out


def test_apply_copies_only_lacking_seeds_that_pass_the_shape_check_and_never_touches_the_old_folder(old, tmp_path, capsys):
    before = digest(old)
    assert audit_mod.main(["--old", str(old), "--apply", "--data-dir", str(tmp_path / "data")]) == 0
    out = capsys.readouterr().out
    assert digest(old) == before
    base = tmp_path / "data" / "library" / "old-templates"
    copied = {p.relative_to(base).as_posix() for p in base.rglob("*.json")}
    assert "function-templates/identity/money-movement.json" in copied and "artifact-templates/brief.json" in copied
    assert "artifact-templates/broken.json" not in copied and "engine-templates/plan.json" not in copied      # not JSON / no version
    assert "warning: broken.json: not a JSON object" in out and "warning: plan.json: missing version" in out
    assert (base / "artifact-templates" / "brief.json").read_bytes() == (old / "artifact-templates" / "brief.json").read_bytes()


def test_a_missing_old_folder_is_refused(tmp_path):
    assert audit_mod.main(["--old", str(tmp_path / "nope")]) == 1


def test_the_real_pro_seeds_are_readable():
    seeds = audit_mod.pro_seeds()
    assert {"identity", "audit"} <= seeds["function-templates"] and "prd" in seeds["artifact-templates"] and "generic" in seeds["engine-templates"]
