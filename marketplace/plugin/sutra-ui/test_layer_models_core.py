"""A4-CORE: the base classes, the bus, the sentences, the containers and the export (C1 to C4)."""
import subprocess
import sys
from pathlib import Path
from typing import Annotated

import pytest
from pydantic import TypeAdapter, ValidationError

import layer_models
from layer_models import bus
from layer_models.base import Closed, Mixin, Open, SutraModel
from layer_models.types import Int, Str

HERE = Path(__file__).resolve().parent


# ---- C1 -------------------------------------------------------------------------------------------------------------------
def test_the_pin():
    import pydantic
    lines = [l.strip() for l in (HERE / "requirements.txt").read_text(encoding="utf-8").splitlines()]
    assert "pydantic==%s" % pydantic.VERSION in lines


def test_r4_an_abstract_class_is_never_made():
    class Base(Open):
        __abstract__ = True
        a: Annotated[str, Str(10)] = None

    class Child(Base):                      # does not declare it: concrete
        pass

    for cls in (SutraModel, Closed, Open, Mixin, Base):
        with pytest.raises(TypeError, match="%s is abstract" % cls.__name__):
            cls()
        with pytest.raises(TypeError, match="is abstract"):
            TypeAdapter(cls).validate_python({})
    assert Child(a="x").a == "x"
    assert TypeAdapter(Child).validate_python({"a": "y"}).a == "y"
    assert "__abstract__" not in Child.__dict__


def test_closed_refuses_an_extra_key_and_open_keeps_it():
    class C(Closed):
        a: Annotated[int, Int()] = None

    class O(Open):
        a: Annotated[int, Int()] = None

    with pytest.raises(ValidationError):
        TypeAdapter(C).validate_python({"a": 1, "zz": 2})
    assert TypeAdapter(O).validate_python({"a": 1, "zz": 2}).model_extra == {"zz": 2}


def test_import_prints_no_warning():
    r = subprocess.run([sys.executable, "-W", "error", "-c", "import layer_models, layer_models.types, layer_models.rules"],
                       capture_output=True, text=True, cwd=str(HERE))
    assert r.returncode == 0, r.stderr
    assert r.stdout == "" and r.stderr == ""


def test_bus_counts_and_reports_what_changed():
    r0 = bus.revision()
    r1 = bus.bump(["x.client"])
    r2 = bus.bump(["x.line", "x.client"])
    assert (r1, r2) == (r0 + 1, r0 + 2) and bus.revision() == r2
    assert bus.changed_since(r0) == ["x.client", "x.line"]
    assert bus.changed_since(r1) == ["x.line", "x.client"]
    assert bus.changed_since(r2) == []
    for i in range(bus.KEEP + 20):
        bus.bump(["k%d" % i])
    assert len(bus._LOG) == bus.KEEP


# ---- C3 -------------------------------------------------------------------------------------------------------------------
import time
import warnings
from typing import Any, Literal, Union

from pydantic import Field

import layer_schema as S
from layer_models import faults as F
from layer_models.types import AnyOf, Bool, Enum, Items, MapOf


def T(n, m=0):
    return Annotated[str, Str(n, m)]


class Three(Closed):
    a: T(5, 1)
    b: T(5, 1)
    c: T(5, 1)
    d: T(5) = None


THREE = S.obj({"a": S.text(5, 1), "b": S.text(5, 1), "c": S.text(5, 1), "d": S.text(5)}, ["a", "b", "c"], open=False)


@pytest.mark.parametrize("value", [
    {}, {"c": 1, "a": 1}, {"d": "toolong", "c": "", "a": "ok"}, {"a": 1, "zz": 1, "b": 2, "c": 3},
    {"zz": 1, "yy": 2}, dict(reversed(list({"a": 1, "b": 2, "c": 3, "d": 4}.items()))),
    {"d": 1, "c": 1, "b": 1, "a": 1, "extra": 1}, "nope", [], None])
def test_missing_keys_come_first_then_the_input_order(value):
    assert F.sentences(TypeAdapter(Three), value) == S.faults(THREE, value)


def test_a_container_fault_comes_before_its_members():
    class Box(Closed):
        xs: Annotated[list[T(2)], Items(2)]
        m: Annotated[dict[str, T(2)], MapOf("^[a-z]+$")] = None
    box = S.obj({"xs": S.items(S.text(2), 2), "m": S.map_of(S.text(2), "^[a-z]+$")}, ["xs"], open=False)
    v = {"m": {"BAD": "abc", "ok": "xyz"}, "xs": ["abc", "d", "efg"]}
    got = F.sentences(TypeAdapter(Box), v)
    assert got == S.faults(box, v)
    assert got.index("$.xs: more than 2 items") < got.index("$.xs[0]: longer than 2")
    assert got.index("$.m.BAD: the key does not match ^[a-z]+$") < got.index("$.m.BAD: longer than 2")


class Rule(Closed):
    kind: Literal["rule"]
    line: T(20, 1)


class Other(Closed):
    kind: Literal["other"]
    note: T(20) = None


FAMILY = Annotated[Union[Rule, Other], Field(discriminator="kind")]


def test_a_union_tag_is_dropped_from_the_path():
    ad = TypeAdapter(FAMILY)
    assert F.sentences(ad, {"kind": "rule"}) == ["$.line: is missing"]
    assert F.sentences(ad, {"kind": "rule", "line": "x" * 21}) == ["$.line: longer than 20"]
    assert F.sentences(ad, {"kind": "other", "note": 5}) == ["$.note: is not a string"]
    assert F.sentences(ad, {"kind": "other", "zz": 1}) == ["$.zz: is not a field here"]

    class Holder(Closed):
        fam: Annotated[list[FAMILY], Items()]
    assert F.sentences(TypeAdapter(Holder), {"fam": [{"kind": "other"}, {"kind": "rule"}]}) == ["$.fam[1].line: is missing"]


def test_a_bad_tag_reads_is_not_one_of():
    ad = TypeAdapter(FAMILY)
    assert F.sentences(ad, {"kind": "zzz"}) == ["$.kind: is not one of rule, other"]
    assert F.sentences(ad, {"line": "a"}) == ["$.kind: is missing"]
    assert F.sentences(ad, "nope") != []


def test_a_pydantic_type_with_no_sentence_is_unmapped():
    class Native(Closed):
        n: int

    ad = TypeAdapter(Native)
    F.UNMAPPED.discard("int_parsing")
    got, unmapped = F.sentences_and_unmapped(ad, {"n": "x"})
    assert got == ["$.n: does not fit"] and unmapped == ["int_parsing"]
    assert "int_parsing" in F.UNMAPPED
    F.UNMAPPED.discard("int_parsing")


def test_the_table_holds_every_type_the_classes_can_raise():
    """Throws a battery of wrong values at classes built from every annotation object; none may leave an unmapped type."""
    class Inner(Open):
        e: Annotated[Any, Enum("a", "b")] = None

    class Rich(Closed):
        s: T(3, 1)
        n: Annotated[int, Int(0, 9)] = None
        b: Annotated[bool, Bool()] = None
        xs: Annotated[list[Inner], Items(2, 1, True)] = None
        m: Annotated[dict[str, Inner], MapOf("^a")] = None
        u: Annotated[Union[T(3), Inner, None], AnyOf()] = None
        o: Inner = None
        fam: FAMILY = None

    ad = TypeAdapter(Rich)
    seen = set()
    for v in (None, [], "x", 1, {}, {"s": 1, "n": "a", "b": 2, "xs": "x", "m": [], "u": 5, "o": 3, "fam": 4},
              {"s": "", "xs": [{"e": "z"}, {"e": "z"}, 3], "m": {"b": {"e": 1}}, "fam": {"kind": "q"}, "zz": 1},
              {"s": "ok", "fam": {}}, {"s": "ok", "o": {"e": 5}, "u": {"e": 1}}):
        _, unmapped = F.sentences_and_unmapped(ad, v)
        seen.update(unmapped)
    assert not seen, "no sentence for pydantic error types %s: add them to faults.TABLE" % sorted(seen)
    assert not F.UNMAPPED


def test_items_returns_the_inner_result():
    class Leaf(Open):
        a: T(3) = None

    class Box(Closed):
        xs: Annotated[list[Leaf], Items(3)]
        m: Annotated[dict[str, Leaf], MapOf()]
        u: Annotated[Union[Leaf, None], AnyOf()] = None
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = TypeAdapter(Box).validate_python({"xs": ({"a": "x"},), "m": {"k": {"a": "y"}}, "u": {"a": "z"}})
        assert isinstance(out.xs[0], Leaf) and isinstance(out.m["k"], Leaf) and isinstance(out.u, Leaf)
        assert out.model_dump() == {"xs": [{"a": "x"}], "m": {"k": {"a": "y"}}, "u": {"a": "z"}}


def test_a_map_of_thousands_of_keys_is_not_quadratic():
    class Leaf(Closed):
        a: T(1)

    class Box(Closed):
        m: Annotated[dict[str, Leaf], MapOf("^k")]
    v = {"m": {("x%d" % i): {"a": "toolong"} for i in range(5000)}}
    ad = TypeAdapter(Box)
    t = time.perf_counter()
    got = F.sentences(ad, v)
    assert time.perf_counter() - t < 1.0
    assert len(got) == 10000 and got[0] == "$.m.x0: the key does not match ^k"
