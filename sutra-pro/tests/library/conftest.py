"""Shared setup for the library tests.

The `toys` fixture builds small families in a PRIVATE registry, so no test touches the app's `REGISTRY`. Nothing here
is autouse: a fixture of this folder must never change what another library test sees.
"""
from types import SimpleNamespace
from typing import Annotated, Literal, Optional

import pytest
from pydantic import Field

from sutra_app.library.base import Record, Value
from sutra_app.library.gate import Gate
from sutra_app.library.registry import ModelRegistry
from sutra_app.library.replies import ReplyParser


def make_toys() -> SimpleNamespace:
    """A fresh registry with these toys registered:

    Thing   Record  family "thing"  kind "thing"            name, count, tags, passed (alias "pass")
    Alpha   Record  family "pair"   kind "alpha"            size
    Beta    Record  family "pair"   kinds "beta", "gamma"   flag
    Doc     Value   payload "doc"                           title, items (list of Item)
    """
    registry = ModelRegistry()

    class Item(Value):
        n: int
        label: Annotated[str, Field(min_length=1, max_length=10)] = "x"

    @registry.register
    class Thing(Record):
        FAMILY = "thing"
        kind: Literal["thing"] = "thing"
        name: Annotated[str, Field(min_length=1, max_length=20)]
        count: Annotated[int, Field(ge=0)] = 0
        tags: Annotated[list[str], Field(max_length=3)] = []
        passed: bool = Field(default=False, alias="pass")
        note: Optional[str] = None

    @registry.register
    class Alpha(Record):
        FAMILY = "pair"
        kind: Literal["alpha"] = "alpha"
        size: int = 0

    @registry.register
    class Beta(Record):
        FAMILY = "pair"
        kind: Literal["beta", "gamma"] = "beta"
        flag: bool = False

    class Doc(Value):
        title: Annotated[str, Field(min_length=1, max_length=30)]
        items: Annotated[list[Item], Field(max_length=5)] = []

    registry.register_payload("doc", 1, Doc)
    return SimpleNamespace(registry=registry, gate=Gate(registry), parser=ReplyParser(registry),
                           Item=Item, Thing=Thing, Alpha=Alpha, Beta=Beta, Doc=Doc)


@pytest.fixture
def toys() -> SimpleNamespace:
    return make_toys()


@pytest.fixture
def toy_factory():
    """`make_toys` itself, for a test that needs a second, identical set."""
    return make_toys
