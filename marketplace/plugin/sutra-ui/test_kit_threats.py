"""test_kit_threats.py -- every APPS-THREATS.md row is mapped in the kit.

The six STRIDE categories and the ten safe-extraction rules (X-1..X-10) must
each have a row in apps-frameworks/THREAT-MAP.md that names at least one check
id present in angles/*.json or states a non-coverage. An unmapped row fails.
"""
import json
import os
import re
import sys
import tempfile
import unittest

os.environ["SUTRA_NATIVE_HOME"] = tempfile.mkdtemp(prefix="kit-threats-native-")
for _m in ("placement_engine", "org_api", "modules_api", "app"):
    sys.modules.pop(_m, None)

UI = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(UI, "apps-frameworks")
sys.path.insert(0, KIT)
import build_kit  # noqa: E402


def _rows(md, section_heading):
    """Return {first cell: whole row} for the table under a heading."""
    out, on = {}, False
    for line in md.splitlines():
        if line.startswith("## "):
            on = section_heading in line
            continue
        if on and line.startswith("|") and not line.startswith("|---") and not line.startswith("| Row") and not line.startswith("| Category") and not line.startswith("| #"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if cells and cells[0]:
                out[cells[0]] = line
    return out


class ThreatMap(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(UI, "APPS-THREATS.md"), encoding="utf-8") as fh:
            cls.threats = fh.read()
        with open(os.path.join(KIT, "THREAT-MAP.md"), encoding="utf-8") as fh:
            cls.tmap = fh.read()
        cls.check_ids = {c["id"] for a in build_kit.load_angles() for c in a["checks"]}

    def _assert_mapped(self, source_rows, map_rows, label):
        self.assertTrue(source_rows, "no %s rows parsed from APPS-THREATS.md" % label)
        for rid in source_rows:
            self.assertIn(rid, map_rows, "%s row %r has no row in THREAT-MAP.md" % (label, rid))
            row = map_rows[rid]
            ids = set(re.findall(r"\bC[0-9]{1,2}\b", row))
            self.assertTrue(ids or "non-coverage" in row, "%s row %r names no check id and no non-coverage" % (label, rid))
            for cid in ids:
                self.assertIn(cid, self.check_ids, "%s row %r names %s which is not a kit check" % (label, rid, cid))

    def test_stride_rows_are_mapped(self):
        self._assert_mapped(_rows(self.threats, "STRIDE"), _rows(self.tmap, "STRIDE rows"), "STRIDE")

    def test_extraction_contract_rows_are_mapped(self):
        self._assert_mapped(_rows(self.threats, "Safe-extraction contract"), _rows(self.tmap, "Safe-extraction contract"), "X")

    def test_map_names_no_unknown_source_rows(self):
        src = set(_rows(self.threats, "STRIDE")) | set(_rows(self.threats, "Safe-extraction contract"))
        mapped = set(_rows(self.tmap, "STRIDE rows")) | set(_rows(self.tmap, "Safe-extraction contract"))
        self.assertEqual(mapped - src, set(), "THREAT-MAP.md maps rows APPS-THREATS.md does not have")


if __name__ == "__main__":
    unittest.main()
