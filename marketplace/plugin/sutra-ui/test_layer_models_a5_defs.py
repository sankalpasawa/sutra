"""A5 P1.5: the 17 definitions of schema version 2 are registered behind the facade, exported as JSON Schema, and the class enforces what
its schema says (qa/a4_equiv.py: the walker over the exported schema against the class, every keyword hit)."""
import io
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "qa"))
import a4_equiv as Q                                             # noqa: E402
import layer_models                                              # noqa: E402
import layer_schema as S                                         # noqa: E402
from layer_models import defs                                    # noqa: E402

A5 = tuple(defs.A5_NAMES)


def test_the_seventeen_follow_the_hundred_and_thirty_in_the_interfaces_order():
    assert len(A5) == 17 and len(set(A5)) == 17 and not set(A5) & set(defs.NAMES)
    assert list(S.DEFS) == list(defs.NAMES) + list(A5) and len(S.DEFS) == 147
    reg = layer_models.load()
    assert all(n in reg.DEF_CLASS for n in A5), "every one is a class"
    assert S.DEFS.dirty is False


def test_each_is_a_closed_object_with_a_generated_json_schema_in_the_interface_file():
    on_disk = json.loads((S.SCHEMA_FOLDER / "interface.v2.json").read_text(encoding="utf-8"))
    for n in A5:
        sch = S.DEFS[n]
        assert sch["type"] == "object" and sch["additionalProperties"] is False and "properties" in sch, n
        assert on_disk["defs"][n] == json.loads(json.dumps(sch)), n


@pytest.mark.parametrize("name", A5)
def test_the_class_enforces_what_its_schema_says(name):
    rep = Q.check(only=[name], fuzz_n=150, out=io.StringIO())[name]
    assert rep["inputs"] > 300 and rep["rejected"] > 100, (name, rep["inputs"], rep["rejected"])
    assert rep["verdict"] == 0 and rep["sentences"] == 0, rep["first"]
    assert rep["missed"] == [], "every keyword the definition has was hit by a rejected input"


def test_the_facade_validates_them_and_a_closed_object_refuses_an_extra_key():
    assert S.validate("dept.request", {"words": "Weekly sales reports"}) == []
    assert S.validate("dept.request", {"words": "x", "colour": "red"}) == ["$.colour: is not a field here"]
    assert S.validate("shadow.open", {"kind": "task", "ref": None}) != []
    with S.expect_refused("dept.request"):
        with pytest.raises(S.SchemaFault):
            S.check("dept.request", {"words": ""})
