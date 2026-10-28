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
