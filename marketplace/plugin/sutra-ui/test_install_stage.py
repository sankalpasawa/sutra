"""install.sh must stage everything the backend imports.

THE BUG THIS FILE EXISTS FOR (2026-09-08). stage_runtime() copied exactly two
things -- sutra-ui/ and lib/ -- and never connectors/. app.py imports
connectors_api, which resolves `connectors.credentials` as parents[1], so every
staged install produced a backend that died at import:

    File ".../connectors_api.py", line 30, in <module>
      from connectors.credentials import KeychainCredentialStore, keychain_available
    ModuleNotFoundError: No module named 'connectors'

It shipped because staging SUCCEEDED. The two assertions in stage_runtime knew
about app.py and placement_engine.py and nothing else, so install.sh printed
success and the failure surfaced at the user's first launch, on a different
machine, as a backend that would not start. Both macOS accounts here hit it the
moment they re-staged.

WHY THE DMG WAS NEVER AFFECTED, and why nobody noticed sooner: the desktop path
is bundle-runtime.sh, which rsyncs the WHOLE plugin tree with excludes rather
than naming directories, so it carried connectors/ all along. Only the
install.sh path enumerates, and enumeration is what rots.

These tests read install.sh as TEXT. They cannot run it -- it builds an app
bundle, an icon and a CLI into the operator's home -- so they assert the copy
list and the guards, which is exactly the layer that was wrong.
"""
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent
INSTALL = HERE / "install.sh"


def _packages_on_the_plugin_root():
    """Importable siblings of sutra-ui/ -- directories with an __init__.py."""
    return sorted(p.name for p in PLUGIN_ROOT.iterdir()
                  if p.is_dir() and (p / "__init__.py").is_file())


def _packages_the_backend_imports():
    """Which of those the sutra-ui Python actually reaches for.

    Scanned rather than listed, so a NEW dependency added tomorrow is covered
    by this test on the day it is added rather than the day someone remembers
    to update a constant here.
    """
    names = _packages_on_the_plugin_root()
    wanted = set()
    for src in HERE.glob("*.py"):
        if src.name.startswith("test_"):
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        for name in names:
            if re.search(r"^\s*(?:from|import)\s+%s\b" % re.escape(name),
                         text, re.M):
                wanted.add(name)
    return sorted(wanted)


class TheStageCopiesWhatTheBackendNeeds(unittest.TestCase):

    def setUp(self):
        self.sh = INSTALL.read_text(encoding="utf-8")
        # stage_runtime() only -- a mention elsewhere in the script is not a copy.
        start = self.sh.index("stage_runtime() {")
        self.stage = self.sh[start:self.sh.index("\n}", start)]

    def test_connectors_is_staged(self):
        """The specific regression. Named as well as covered by the sweep
        below, so a failure says which package rather than 'some package'."""
        self.assertIn("$PLUGIN_REPO/connectors", self.stage)

    def test_lib_is_staged(self):
        self.assertIn("$PLUGIN_REPO/lib", self.stage)

    def test_every_sibling_package_the_backend_imports_is_staged(self):
        """The general rule. connectors/ was the instance; this is the class."""
        missing = [name for name in _packages_the_backend_imports()
                   if ("$PLUGIN_REPO/%s" % name) not in self.stage]
        self.assertEqual(missing, [], (
            "sutra-ui imports these sibling packages but install.sh does not "
            "stage them, so a staged install will die at import: %s" % missing))

    def test_the_sweep_actually_found_something(self):
        """A scan that silently matches nothing would make the test above pass
        for every possible install.sh. connectors is the known member."""
        found = _packages_the_backend_imports()
        self.assertIn("connectors", found)

    def test_each_staged_package_is_asserted_after_the_copy(self):
        """A copy without an assertion is how this shipped: rsync of a missing
        source can leave an empty directory and rsync still exits 0."""
        self.assertIn("$STAGE_CONN/credentials/__init__.py", self.stage)
        self.assertIn("$STAGE_LIB/placement_engine.py", self.stage)


class TheStageIsProvenByImportingIt(unittest.TestCase):
    """The assertions above test PARTS. The check this guards asks the only
    question that matters, and is what makes the next forgotten dependency fail
    on the installing machine instead of the user's."""

    def setUp(self):
        self.sh = INSTALL.read_text(encoding="utf-8")

    def test_install_imports_the_staged_backend_before_declaring_success(self):
        self.assertRegex(self.sh, r'cd "\$SRC" && "\$PY" -c "import app"')

    def test_a_backend_that_cannot_import_stops_the_install(self):
        i = self.sh.index('-c "import app"')
        self.assertIn("die", self.sh[i:i + 400],
                      "the import check must abort, not warn")

    def test_it_runs_after_the_venv_exists(self):
        """It needs both halves: the staged tree AND an interpreter with the
        dependencies in it. Ordered wrong, it would fail on every clean box."""
        self.assertLess(self.sh.index('step "venv"'),
                        self.sh.index('-c "import app"'))


class TheConnectorPackageIsStillHere(unittest.TestCase):
    """96edce8 removed connectors/ entirely ("clean slate for the rewrite") and
    c234997 brought it back with the platform rewrite. connectors_api.py never
    stopped importing it in between. If it is ever deleted again, this fails
    here rather than as a dead backend on someone's Mac."""

    def test_the_package_the_backend_imports_exists(self):
        self.assertTrue((PLUGIN_ROOT / "connectors" / "credentials"
                         / "__init__.py").is_file())

    def test_connectors_api_still_has_a_package_to_import(self):
        src = (HERE / "connectors_api.py").read_text(encoding="utf-8")
        self.assertIn("from connectors.credentials import", src)


if __name__ == "__main__":
    unittest.main()
