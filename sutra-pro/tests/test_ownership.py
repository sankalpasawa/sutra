"""D99: nothing of this product names a person. The repository's own audit (scripts/ownership-audit.sh at the repository root, D69)
fails on two identifiers anywhere outside its allowlist; this runs the same search over this folder and this product's workflows,
tracked or not yet added, so a path pasted into a doc fails here, in this product's CI, before it fails a gate nobody here reads."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# the two identifiers, spelled in pieces so that this file does not contain them either
PATTERN = "tchan" "drakar" "|" "tis" "hant"


def toplevel() -> Path | None:
    if shutil.which("git") is None:
        return None
    done = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--show-toplevel"], capture_output=True, text=True, encoding="utf-8")
    return Path(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip() else None


def test_no_file_of_this_product_names_a_person():
    top = toplevel()
    if top is None:
        pytest.skip("not inside a git work tree (an sdist, a copy)")
    folder = ROOT.relative_to(top).as_posix() or "."
    done = subprocess.run(["git", "-C", str(top), "grep", "--untracked", "-nIiE", PATTERN, "--", folder, ".github/workflows/sutra-pro-*.yml"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert done.returncode in (0, 1), done.stderr
    assert done.stdout.strip() == "", "a personal identifier is in a file of this product (use ~ for a home folder):\n" + done.stdout
