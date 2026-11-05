"""The model registry (library design 3.3) and the schema export (`export.py`, flow F5)."""
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pytest
from pydantic import Field, ValidationError

from sutra_app.library import export
from sutra_app.library.base import Record, Value
from sutra_app.library.registry import REGISTRY, ModelRegistry, RegistryError, record


def fresh_class(registry_family: str, kinds, version: int = 1, **fields):
    """A Record class with the given family, kind(s) and version, built on the spot."""
    ns = {"FAMILY": registry_family, "VERSION": version, "__annotations__": {"kind": Literal[tuple(kinds)]}}
    ns["kind"] = kinds[0]
    ns["__annotations__"]["schema_version"] = int
    ns["schema_version"] = version
    for name, default in fields.items():
        ns["__annotations__"][name] = type(default)
        ns[name] = default
    return type("Cls_" + "_".join(kinds), (Record,), ns)


def code_of(exc_info) -> str:
    return exc_info.value.code


# ---- register, lookup, versions ---------------------------------------------------------------------------------------

def test_register_adds_one_entry_per_kind(toys):
    reg = toys.registry
    assert reg.families() == ["doc", "pair", "thing"]
    assert reg.versions("thing") == [1]
    assert reg.kinds("thing") == {"thing": toys.Thing}
    assert reg.kinds("pair") == {"alpha": toys.Alpha, "beta": toys.Beta, "gamma": toys.Beta}


def test_register_returns_the_class_so_it_works_as_a_decorator():
    reg = ModelRegistry()

    @reg.register
    class One(Record):
        FAMILY = "one"
        kind: Literal["one"] = "one"

    assert One.__name__ == "One" and reg.kinds("one") == {"one": One}


def test_the_module_level_decorator_is_the_global_registrys_register():
    assert record == REGISTRY.register
    assert isinstance(REGISTRY, ModelRegistry)


def test_registering_the_same_class_twice_is_harmless(toys):
    toys.registry.register(toys.Thing)
    assert toys.registry.kinds("thing") == {"thing": toys.Thing}


def test_the_same_family_version_and_kind_with_another_class_is_a_duplicate(toys):
    clash = fresh_class("thing", ["thing"])
    with pytest.raises(RegistryError) as e:
        toys.registry.register(clash)
    assert code_of(e) == "duplicate" and "duplicate" in str(e.value)
    assert toys.registry.kinds("thing") == {"thing": toys.Thing}


def test_a_duplicate_registers_none_of_its_kinds():
    reg = ModelRegistry()
    reg.register(fresh_class("fam", ["a"]))
    both = fresh_class("fam", ["fresh", "a"])
    with pytest.raises(RegistryError) as e:
        reg.register(both)
    assert code_of(e) == "duplicate"
    assert sorted(reg.kinds("fam")) == ["a"]


def test_a_new_kind_in_an_existing_family_is_additive(toys):
    extra = fresh_class("pair", ["delta"])
    toys.registry.register(extra)
    assert toys.registry.versions("pair") == [1]
    assert sorted(toys.registry.kinds("pair")) == ["alpha", "beta", "delta", "gamma"]


def test_versions_are_sorted_and_the_latest_is_the_default():
    reg = ModelRegistry()
    v2 = reg.register(fresh_class("fam", ["a"], version=2, marker=2))
    v1 = reg.register(fresh_class("fam", ["a"], version=1, marker=1))
    assert reg.versions("fam") == [1, 2]
    assert reg.kinds("fam") == {"a": v2} and reg.kinds("fam", 1) == {"a": v1} and reg.kinds("fam", 2) == {"a": v2}


def test_kinds_returns_a_copy(toys):
    toys.registry.kinds("pair").clear()
    assert len(toys.registry.kinds("pair")) == 3


def test_abstract_classes_are_skipped_but_their_children_are_registered():
    reg = ModelRegistry()

    @reg.register
    class Base(Record):
        FAMILY = "tree"
        ABSTRACT = True
        kind: str = "base"

    @reg.register
    class Child(Base):
        kind: Literal["child"] = "child"

    assert reg.kinds("tree") == {"child": Child}


def test_an_abstract_class_alone_registers_nothing():
    reg = ModelRegistry()
    reg.register(type("Abs", (Record,), {"ABSTRACT": True, "__annotations__": {}}))
    assert reg.families() == []


def test_a_class_with_the_next_version_that_does_not_redeclare_schema_version_is_refused_when_registered():
    # Review round 1: it used to register, and then every V2() and every v2 payload failed with "schema_version is 1,
    # this class is version 2" at its first write.
    class V1(Record):
        FAMILY = "vv"
        kind: Literal["vv"] = "vv"

    class V2(Record):
        FAMILY = "vv"
        VERSION = 2
        kind: Literal["vv"] = "vv"

    reg = ModelRegistry()
    reg.register(V1)
    with pytest.raises(RegistryError) as e:
        reg.register(V2)
    assert code_of(e) == "bad_schema_version"
    assert "V2" in str(e.value) and "VERSION is 2" in str(e.value) and "defaults to 1" in str(e.value)
    assert "schema_version: int = 2" in str(e.value)
    assert reg.versions("vv") == [1] and reg.kinds("vv") == {"vv": V1}          # nothing was half registered


def test_a_schema_version_default_must_be_the_classs_own_version():
    class Right(Record):
        FAMILY = "right"
        VERSION = 3
        kind: Literal["right"] = "right"
        schema_version: int = 3

    class Narrow(Record):
        FAMILY = "narrow"
        VERSION = 2
        kind: Literal["narrow"] = "narrow"
        schema_version: Literal[2] = 2

    class Wrong(Record):
        FAMILY = "wrong"
        kind: Literal["wrong"] = "wrong"
        schema_version: int = 3                       # VERSION is 1

    class Required(Record):
        FAMILY = "required"
        kind: Literal["required"] = "required"
        schema_version: int                           # no default at all

    class Made(Record):
        FAMILY = "made"
        kind: Literal["made"] = "made"
        schema_version: int = Field(default_factory=lambda: 1)

    reg = ModelRegistry()
    reg.register(Right)
    reg.register(Narrow)
    assert reg.versions("right") == [3] and reg.versions("narrow") == [2]
    for bad, shown in ((Wrong, "defaults to 3"), (Required, "no usable default"), (Made, "no usable default")):
        with pytest.raises(RegistryError) as e:
            reg.register(bad)
        assert code_of(e) == "bad_schema_version" and shown in str(e.value), bad
    assert reg.families() == ["narrow", "right"]


def test_a_boolean_is_not_a_schema_version_default():
    class Truthy(Record):
        FAMILY = "truthy"
        kind: Literal["truthy"] = "truthy"
        schema_version: bool = True                   # True == 1

    with pytest.raises(RegistryError) as e:
        ModelRegistry().register(Truthy)
    assert code_of(e) == "bad_schema_version"


def test_the_schema_version_default_is_not_looked_at_for_an_abstract_class():
    reg = ModelRegistry()

    @reg.register
    class Base(Record):
        FAMILY = "tree"
        VERSION = 2
        ABSTRACT = True
        kind: str = "base"                            # schema_version defaults to 1 here, and nobody registers this class

    @reg.register
    class Child(Base):
        kind: Literal["child"] = "child"
        schema_version: int = 2

    assert reg.versions("tree") == [2] and reg.kinds("tree") == {"child": Child}


def test_unknown_family_and_version_are_registry_errors(toys):
    for call in (lambda: toys.registry.versions("nope"), lambda: toys.registry.kinds("nope"),
                 lambda: toys.registry.adapter("nope"), lambda: toys.registry.json_schema("nope"),
                 lambda: toys.registry.transport_schema("nope"), lambda: toys.registry.is_payload("nope"),
                 lambda: toys.registry.versions(None), lambda: toys.registry.versions(["thing"])):
        with pytest.raises(RegistryError) as e:
            call()
        assert code_of(e) == "unknown_family"
    for call in (lambda: toys.registry.kinds("thing", 2), lambda: toys.registry.adapter("thing", 0),
                 lambda: toys.registry.rules("thing", 7)):
        with pytest.raises(RegistryError) as e:
            call()
        assert code_of(e) == "unknown_version"


@pytest.mark.parametrize("cls, code", [
    (int, "not_record"),
    (Value, "not_record"),
    ("Thing", "not_record"),
    (type("NoFamily", (Record,), {"__annotations__": {"kind": Literal["x"]}, "kind": "x"}), "bad_family"),
    (type("BadFamily", (Record,), {"FAMILY": "Bad Name", "__annotations__": {"kind": Literal["x"]}, "kind": "x"}), "bad_family"),
    (type("SlashFamily", (Record,), {"FAMILY": "a/b", "__annotations__": {"kind": Literal["x"]}, "kind": "x"}), "bad_family"),
    (type("EmptyFamily", (Record,), {"FAMILY": "", "__annotations__": {"kind": Literal["x"]}, "kind": "x"}), "bad_family"),
    (type("LongFamily", (Record,), {"FAMILY": "a" * 81, "__annotations__": {"kind": Literal["x"]}, "kind": "x"}), "bad_family"),
    (type("VersionZero", (Record,), {"FAMILY": "f", "VERSION": 0, "__annotations__": {"kind": Literal["x"]}, "kind": "x"}), "bad_version"),
    (type("VersionText", (Record,), {"FAMILY": "f", "VERSION": "1", "__annotations__": {"kind": Literal["x"]}, "kind": "x"}), "bad_version"),
    (type("VersionBool", (Record,), {"FAMILY": "f", "VERSION": True, "__annotations__": {"kind": Literal["x"]}, "kind": "x"}), "bad_version"),
    (type("PlainKind", (Record,), {"FAMILY": "f", "__annotations__": {"kind": str}, "kind": "x"}), "kind_not_literal"),
    (type("IntKind", (Record,), {"FAMILY": "f", "__annotations__": {"kind": Literal[1, 2]}, "kind": 1}), "kind_not_literal"),
    (type("EmptyKind", (Record,), {"FAMILY": "f", "__annotations__": {"kind": Literal[""]}, "kind": ""}), "kind_not_literal"),
])
def test_what_cannot_be_registered(cls, code):
    reg = ModelRegistry()
    with pytest.raises(RegistryError) as e:
        reg.register(cls)
    assert code_of(e) == code
    assert reg.families() == []


def test_a_family_name_may_hold_dots_dashes_and_underscores_but_no_path_separator():
    reg = ModelRegistry()
    for name in ("a", "atom_ledger_row", "artifact.prd.problem", "a-b", "x" * 80):
        reg.register(fresh_class(name, ["k"]))
    assert len(reg.families()) == 5


def test_a_record_family_and_a_payload_cannot_share_a_name(toys):
    class Shadow(Value):
        x: int = 0

    with pytest.raises(RegistryError) as e:
        toys.registry.register_payload("thing", 1, Shadow)
    assert code_of(e) == "family_conflict"
    with pytest.raises(RegistryError) as e:
        toys.registry.register(fresh_class("doc", ["doc"]))
    assert code_of(e) == "family_conflict"


# ---- freeze ------------------------------------------------------------------------------------------------------------

def test_freeze_refuses_every_later_registration(toys):
    reg = toys.registry
    assert reg.frozen is False
    reg.freeze()
    assert reg.frozen is True
    reg.freeze()                                              # idempotent
    class Late(Value):
        x: int = 0
    for call in (lambda: reg.register(fresh_class("late", ["late"])), lambda: reg.register(toys.Thing),
                 lambda: reg.register_payload("late", 1, Late), lambda: reg.upgrade("thing", 1)(lambda d: d)):
        with pytest.raises(RegistryError) as e:
            call()
        assert code_of(e) == "frozen" and "frozen" in str(e.value)
    assert reg.families() == ["doc", "pair", "thing"]


def test_a_frozen_registry_still_answers_lookups(toys):
    toys.registry.freeze()
    assert toys.registry.kinds("thing") and toys.registry.adapter("pair") and toys.registry.json_schema("doc")


def test_freeze_checks_that_every_upgrade_leads_somewhere():
    reg = ModelRegistry()
    reg.register(fresh_class("fam", ["a"], version=1))
    reg.upgrade("fam", 1)(lambda d: d)                        # there is no version 2
    with pytest.raises(RegistryError) as e:
        reg.freeze()
    assert code_of(e) == "dangling_upgrade" and reg.frozen is False
    reg.register(fresh_class("fam", ["a"], version=2))        # still open, so the fix is possible
    reg.freeze()
    assert reg.frozen is True


# ---- adapters and schemas ---------------------------------------------------------------------------------------------

def test_a_family_with_one_class_validates_that_class(toys):
    adapter = toys.registry.adapter("thing")
    model = adapter.validate_python({"kind": "thing", "name": "n"})
    assert type(model) is toys.Thing and model.count == 0
    with pytest.raises(ValidationError) as e:
        adapter.validate_python({"kind": "other", "name": "n"})
    assert [x["type"] for x in e.value.errors()] == ["literal_error"]


def test_a_family_with_several_classes_is_a_union_discriminated_by_kind(toys):
    adapter = toys.registry.adapter("pair")
    assert type(adapter.validate_python({"kind": "alpha", "size": 3})) is toys.Alpha
    assert type(adapter.validate_python({"kind": "gamma"})) is toys.Beta
    with pytest.raises(ValidationError) as e:
        adapter.validate_python({"kind": "delta"})
    assert [x["type"] for x in e.value.errors()] == ["union_tag_invalid"]
    with pytest.raises(ValidationError) as e:
        adapter.validate_python({"size": 3})
    assert [x["type"] for x in e.value.errors()] == ["union_tag_not_found"]
    with pytest.raises(ValidationError) as e:
        adapter.validate_python({"kind": "alpha", "size": "3"})
    assert [(x["type"], x["loc"]) for x in e.value.errors()] == [("int_type", ("alpha", "size"))]       # the tag comes first


def test_adapters_are_built_once(toys):
    assert toys.registry.adapter("pair") is toys.registry.adapter("pair")
    assert toys.registry.adapter("pair") is toys.registry.adapter("pair", 1)


def test_a_new_registration_replaces_the_cached_adapter(toys):
    before = toys.registry.adapter("pair")
    toys.registry.register(fresh_class("pair", ["delta"], size=1))
    after = toys.registry.adapter("pair")
    assert after is not before
    assert after.validate_python({"kind": "delta"}).kind == "delta"
    assert toys.registry.adapter("thing") is toys.registry.adapter("thing")


def test_json_schema_of_a_single_class_and_of_a_family(toys):
    single = toys.registry.json_schema("thing")
    assert single["properties"]["kind"]["const"] == "thing"
    assert "pass" in single["properties"] and "passed" not in single["properties"]              # by alias
    family = toys.registry.json_schema("pair")
    assert family["discriminator"]["propertyName"] == "kind"
    assert set(family["discriminator"]["mapping"]) == {"alpha", "beta", "gamma"}
    assert len(family["oneOf"]) == 2


def test_transport_schema_needs_a_kind_when_a_family_has_several_classes(toys):
    reg = toys.registry
    assert reg.transport_schema("thing")["properties"]["kind"]["enum"] == ["thing"]
    assert reg.transport_schema("pair", kind="alpha")["properties"]["size"] == {"type": "integer"}
    assert reg.transport_schema("pair", kind="gamma") == reg.transport_schema("pair", kind="beta")      # one class, two kinds
    with pytest.raises(RegistryError) as e:
        reg.transport_schema("pair")
    assert code_of(e) == "kind_required"
    with pytest.raises(RegistryError) as e:
        reg.transport_schema("pair", kind="omega")
    assert code_of(e) == "unknown_kind"


def test_each_kind_gets_its_own_transport_schema_even_when_cached(toys):
    reg = toys.registry
    alpha, beta = reg.transport_schema("pair", kind="alpha"), reg.transport_schema("pair", kind="beta")
    assert "size" in alpha["properties"] and "flag" not in alpha["properties"]
    assert "flag" in beta["properties"] and "size" not in beta["properties"]
    assert reg.transport_schema("pair", kind="alpha") == alpha and reg.transport_schema("pair", kind="gamma") == beta
    assert reg.transport_schema("thing") != alpha


def test_transport_schema_is_computed_once_per_class(toys, monkeypatch):
    from sutra_app.library import registry as registry_module
    calls = []
    real = registry_module.transport_schema
    monkeypatch.setattr(registry_module, "transport_schema", lambda cls: calls.append(cls) or real(cls))
    for _ in range(3):
        toys.registry.transport_schema("pair", kind="alpha")
        toys.registry.transport_schema("pair", kind="gamma")
        toys.registry.transport_schema("pair", kind="beta")
    assert calls == [toys.Alpha, toys.Beta]


def test_transport_schema_returns_a_copy_each_time(toys):
    first = toys.registry.transport_schema("thing")
    first["required"].clear()
    assert toys.registry.transport_schema("thing")["required"] != []


def test_transport_schema_follows_the_version_and_forgets_on_new_registrations():
    reg = ModelRegistry()
    reg.register(fresh_class("fam", ["a"], version=1, one=1))
    old = reg.transport_schema("fam")
    assert "one" in old["properties"]
    reg.register(fresh_class("fam", ["a"], version=2, two=2))
    assert "two" in reg.transport_schema("fam")["properties"]
    assert reg.transport_schema("fam", version=1) == old


# ---- payloads -------------------------------------------------------------------------------------------------------

def test_a_payload_is_a_family_with_one_kind_named_after_it(toys):
    reg = toys.registry
    assert reg.is_payload("doc") and not reg.is_payload("thing")
    assert reg.kinds("doc") == {"doc": toys.Doc} and reg.versions("doc") == [1]
    model = reg.adapter("doc").validate_python({"title": "t", "items": [{"n": 1}]})
    assert type(model) is toys.Doc
    assert reg.transport_schema("doc")["properties"]["title"] == {"type": "string"}
    assert reg.json_schema("doc")["properties"]["items"]["maxItems"] == 5


def test_a_new_payload_version_replaces_the_cached_adapter_and_becomes_the_latest():
    reg = ModelRegistry()

    class One(Value):
        a: int = 0

    class Two(Value):
        b: int = 0

    reg.register_payload("section", 1, One)
    first = reg.adapter("section")
    assert first.validate_python({"a": 1}).a == 1
    reg.register_payload("section", 2, Two)
    assert reg.adapter("section") is not first and reg.adapter("section", 1) is not reg.adapter("section", 2)
    assert reg.adapter("section").validate_python({"b": 2}).b == 2 and reg.versions("section") == [1, 2]
    assert reg.kinds("section") == {"section": Two} and reg.kinds("section", 1) == {"section": One}


def test_payload_rules_are_attached_per_version_and_read_back():
    reg = ModelRegistry()

    class Section(Value):
        text: str = ""

    rule_a, rule_b = SimpleNamespace(name="a"), SimpleNamespace(name="b")
    reg.register_payload("section", 1, Section, rules=[rule_a])
    reg.register_payload("section", 2, Section, rules=(rule_a, rule_b))
    assert reg.rules("section", 1) == (rule_a,) and reg.rules("section") == (rule_a, rule_b)
    reg.register_payload("bare", 1, Section)
    assert reg.rules("bare") == ()


def test_registering_the_same_payload_again_is_harmless_unless_it_changes():
    reg = ModelRegistry()

    class Section(Value):
        text: str = ""

    rule = SimpleNamespace(name="r")
    reg.register_payload("section", 1, Section, rules=[rule])
    reg.register_payload("section", 1, Section, rules=[rule])
    with pytest.raises(RegistryError) as e:
        reg.register_payload("section", 1, Section, rules=[])
    assert code_of(e) == "duplicate"

    class Other(Value):
        text: str = ""

    with pytest.raises(RegistryError) as e:
        reg.register_payload("section", 1, Other, rules=[rule])
    assert code_of(e) == "duplicate"
    assert reg.kinds("section") == {"section": Section}


@pytest.mark.parametrize("name, version, cls_factory, code", [
    ("p", 1, lambda: fresh_class("x", ["x"]), "not_payload"),
    ("p", 1, lambda: int, "not_payload"),
    ("P", 1, lambda: type("V", (Value,), {}), "bad_family"),
    ("p/q", 1, lambda: type("V", (Value,), {}), "bad_family"),
    ("p", 0, lambda: type("V", (Value,), {}), "bad_version"),
    ("p", "1", lambda: type("V", (Value,), {}), "bad_version"),
])
def test_what_cannot_be_registered_as_a_payload(name, version, cls_factory, code):
    reg = ModelRegistry()
    with pytest.raises(RegistryError) as e:
        reg.register_payload(name, version, cls_factory())
    assert code_of(e) == code and reg.families() == []


# ---- the upgrade chain ----------------------------------------------------------------------------------------------

def make_versions(reg: ModelRegistry, count: int):
    for version in range(1, count + 1):
        reg.register(fresh_class("fam", ["a"], version=version, **{f"field{version}": version}))


def test_upgrade_functions_are_chained_from_the_payloads_version():
    reg = ModelRegistry()
    make_versions(reg, 3)
    calls = []

    @reg.upgrade("fam", 1)
    def one_to_two(payload):
        calls.append(1)
        return {**payload, "field2": 22}

    @reg.upgrade("fam", 2)
    def two_to_three(payload):
        calls.append(2)
        return {**payload, "field3": payload["field2"] + 1}

    assert reg.can_upgrade("fam", 1, 3) and reg.can_upgrade("fam", 2, 3) and reg.can_upgrade("fam", 3, 3)
    out = reg.upgrade_payload("fam", {"kind": "a", "schema_version": 1, "field1": 1}, 1)
    assert out == {"kind": "a", "schema_version": 3, "field1": 1, "field2": 22, "field3": 23} and calls == [1, 2]
    calls.clear()
    assert reg.upgrade_payload("fam", {"kind": "a", "schema_version": 2, "field2": 5}, 2, 3)["field3"] == 6 and calls == [2]
    assert reg.upgrade_payload("fam", {"kind": "a"}, 1, 2)["schema_version"] == 2
    assert reg.upgrade_payload("fam", {"k": 1}, 3, 3) == {"k": 1}


def test_a_payload_family_can_be_upgraded_too_without_a_schema_version_being_invented():
    reg = ModelRegistry()

    class One(Value):
        a: int = 0

    class Two(Value):
        b: int = 0

    reg.register_payload("section", 1, One)
    reg.register_payload("section", 2, Two)
    reg.upgrade("section", 1)(lambda payload: {"b": payload["a"] + 1})
    assert reg.upgrade_payload("section", {"a": 1}, 1) == {"b": 2}


def test_upgrade_never_changes_the_callers_data_and_sets_the_schema_version_itself():
    reg = ModelRegistry()
    make_versions(reg, 2)

    @reg.upgrade("fam", 1)
    def mutating(payload):
        payload["nested"]["x"] = 1
        payload["schema_version"] = 99                    # the registry decides the version, not the function
        return payload

    original = {"kind": "a", "nested": {"x": 0}}
    out = reg.upgrade_payload("fam", original, 1)
    assert original == {"kind": "a", "nested": {"x": 0}} and out["nested"] == {"x": 1} and out["schema_version"] == 2


def test_a_missing_step_and_a_bad_return_are_registry_errors():
    reg = ModelRegistry()
    make_versions(reg, 3)
    reg.upgrade("fam", 2)(lambda payload: [payload])
    assert reg.can_upgrade("fam", 2, 3) and not reg.can_upgrade("fam", 1, 3) and not reg.can_upgrade("fam", 1, 2)
    with pytest.raises(RegistryError) as e:
        reg.upgrade_payload("fam", {}, 1)
    assert code_of(e) == "no_upgrade"
    with pytest.raises(RegistryError) as e:
        reg.upgrade_payload("fam", {}, 2)
    assert code_of(e) == "bad_upgrade"


def test_upgrade_registration_is_checked():
    reg = ModelRegistry()
    make_versions(reg, 2)
    reg.upgrade("fam", 1)(lambda payload: payload)
    with pytest.raises(RegistryError) as e:
        reg.upgrade("fam", 1)(lambda payload: payload)
    assert code_of(e) == "duplicate_upgrade"
    for call, code in ((lambda: reg.upgrade("ghost", 1)(lambda p: p), "unknown_family"),
                       (lambda: reg.upgrade("fam", -1)(lambda p: p), "bad_version"),
                       (lambda: reg.upgrade("fam", True)(lambda p: p), "bad_version"),
                       (lambda: reg.upgrade("fam", "1")(lambda p: p), "bad_version"),
                       (lambda: reg.upgrade("fam", 0)("not callable"), "bad_upgrade")):
        with pytest.raises(RegistryError) as e:
            call()
        assert code_of(e) == code


def test_the_upgrade_decorator_returns_the_function():
    reg = ModelRegistry()
    make_versions(reg, 2)

    def step(payload):
        return payload

    assert reg.upgrade("fam", 1)(step) is step


# ---- verify_refs ----------------------------------------------------------------------------------------------------

def spec(function, task_kinds=(), templates=()):
    return SimpleNamespace(function=function, task_kinds=list(task_kinds), atom_templates=list(templates))


def task_kind(kind, family, reply_kind):
    return SimpleNamespace(kind=kind, reply_family=family, reply_kind=reply_kind)


def template(name, *checks):
    return SimpleNamespace(name=name, checks=[SimpleNamespace(name=n, args=list(a)) for n, a in checks])


def arity(name):
    return {"reply-valid": (2, 2), "answer-recorded": (1, 1), "turn-posted": (0, 0)}.get(name)


def test_verify_refs_accepts_references_that_resolve(toys):
    specs = SimpleNamespace(specs={
        "identity": spec("identity", [task_kind("intake", "pair", "alpha"), task_kind("any", "pair", "alpha|beta|gamma"),
                                      task_kind("none", "", "")],
                         [template("t", ("reply-valid", ["pair", "alpha"]), ("turn-posted", []), ("answer-recorded", ["m1"]))])})
    assert toys.registry.verify_refs(specs, check_arity=arity) == []


def test_verify_refs_flags_a_missing_family_and_each_missing_alternative(toys):
    specs = [spec("identity", [task_kind("one", "ghost", "x"), task_kind("two", "pair", "alpha|omega| beta |zeta"),
                               task_kind("three", "pair", ""), task_kind("four", "", "alpha")])]
    found = {(v.path, v.code) for v in toys.registry.verify_refs(specs)}
    assert found == {
        ("identity.task_kinds.one.reply_family", "unknown_reply_family"),
        ("identity.task_kinds.two.reply_kind", "unknown_reply_kind"),
        ("identity.task_kinds.three", "incomplete_reply_ref"),
        ("identity.task_kinds.four", "incomplete_reply_ref"),
    }
    messages = [v.message for v in toys.registry.verify_refs(specs) if v.code == "unknown_reply_kind"]
    assert len(messages) == 2 and any("'omega'" in m for m in messages) and any("'zeta'" in m for m in messages)


def test_verify_refs_uses_the_latest_version_of_a_family():
    reg = ModelRegistry()
    reg.register(fresh_class("fam", ["old"], version=1))
    reg.register(fresh_class("fam", ["new"], version=2))
    bad = reg.verify_refs([spec("f", [task_kind("k", "fam", "old")])])
    assert [v.code for v in bad] == ["unknown_reply_kind"]
    assert reg.verify_refs([spec("f", [task_kind("k", "fam", "new")])]) == []


def test_verify_refs_checks_check_names_and_argument_counts_when_it_has_an_arity_function(toys):
    specs = [spec("audit", templates=[template("tmpl", ("reply-valid", ["only-one"]), ("turn-posted", ["x"]),
                                                ("answer-recorded", []), ("mystery", []), ("reply-valid", ["a", "b"]))])]
    found = [(v.path, v.code) for v in toys.registry.verify_refs(specs, check_arity=arity)]
    assert found == [
        ("audit.atom_templates.tmpl.checks.0.args", "bad_check_args"),
        ("audit.atom_templates.tmpl.checks.1.args", "bad_check_args"),
        ("audit.atom_templates.tmpl.checks.2.args", "bad_check_args"),
        ("audit.atom_templates.tmpl.checks.3.name", "unknown_check"),
    ]
    with pytest.raises(RegistryError) as e:                              # without an arity function: not a quiet pass
        toys.registry.verify_refs(specs)
    assert code_of(e) == "arity_unbound" and "audit.atom_templates.tmpl.checks.0" in str(e.value)
    assert "check_arity" in str(e.value) and "bind_check_arity" in str(e.value)
    ranged = toys.registry.verify_refs(specs, check_arity=lambda n: (1, 3) if n != "mystery" else None)
    assert [v.code for v in ranged] == ["bad_check_args", "unknown_check"]
    assert "takes 1 to 3 arguments, got 0" in ranged[0].message


def test_verify_refs_finds_specs_where_they_were_bound(toys):
    reg = toys.registry
    with pytest.raises(RegistryError) as e:                             # nothing bound: it says so, it does not pass
        reg.verify_refs()
    assert code_of(e) == "specs_unbound" and "bind_function_specs" in str(e.value)
    bad = [spec("identity", [task_kind("k", "ghost", "x")])]
    reg.bind_function_specs(lambda: bad)                                # a loader
    assert [v.code for v in reg.verify_refs()] == ["unknown_reply_family"]
    reg.bind_function_specs(bad)                                        # or the object itself
    assert [v.code for v in reg.verify_refs()] == ["unknown_reply_family"]
    reg.bind_function_specs(None)
    with pytest.raises(RegistryError) as e:
        reg.verify_refs()
    assert code_of(e) == "specs_unbound"
    reg.bind_check_arity(arity)
    named = [spec("a", templates=[template("t", ("nope", []))])]
    assert [v.code for v in reg.verify_refs(named)] == ["unknown_check"]
    assert reg.verify_refs(named, check_arity=lambda n: (0, 0)) == []     # the argument wins over the bound function


def test_verify_refs_accepts_a_mapping_or_a_list_of_specs(toys):
    one = spec("identity", [task_kind("k", "ghost", "x")])
    assert len(toys.registry.verify_refs({"identity": one})) == 1
    assert len(toys.registry.verify_refs([one, one])) == 2
    assert toys.registry.verify_refs([spec("empty")]) == []


def test_verify_refs_never_passes_because_there_was_nothing_to_look_at(toys):
    # Review round 1: it returned [] for no specs at all, so "verify_refs against the full registry" passed vacuously
    # until someone bound the specs. An empty list now means at least one spec was looked at.
    reg = toys.registry
    for nothing in ([], {}, (), SimpleNamespace(specs={}), SimpleNamespace(specs=[])):
        with pytest.raises(RegistryError) as e:
            reg.verify_refs(nothing)
        assert code_of(e) == "specs_empty", nothing
    reg.bind_function_specs(lambda: [])                                 # a loader that found nothing
    with pytest.raises(RegistryError) as e:
        reg.verify_refs()
    assert code_of(e) == "specs_empty"
    reg.bind_function_specs(lambda: None)                               # a loader that returned nothing at all
    with pytest.raises(RegistryError) as e:
        reg.verify_refs()
    assert code_of(e) == "specs_unbound"
    assert reg.verify_refs([spec("empty")]) == []                       # one spec, nothing wrong in it: really checked


def test_verify_refs_says_a_bad_reference_when_one_spec_holds_one(toys):
    reg = toys.registry
    assert len(reg.verify_refs([spec("a", [task_kind("k", "ghost", "x")])])) == 1
    assert reg.verify_refs([spec("a", [task_kind("k", "pair", "alpha")])]) == []


def test_verify_refs_does_not_ask_for_an_arity_function_when_no_spec_holds_a_check(toys):
    specs = [spec("a", [task_kind("k", "pair", "alpha")], templates=[template("t")]), spec("b")]
    assert toys.registry.verify_refs(specs) == []
    toys.registry.bind_check_arity(arity)
    toys.registry.bind_check_arity(None)                                # unbound again
    assert toys.registry.verify_refs(specs) == []
    with_check = [spec("a", templates=[template("t", ("turn-posted", []))])]
    with pytest.raises(RegistryError) as e:
        toys.registry.verify_refs(with_check)
    assert code_of(e) == "arity_unbound"


def test_verify_refs_can_be_told_to_accept_every_check_so_only_the_reply_references_are_looked_at(toys):
    specs = [spec("a", [task_kind("k", "ghost", "x")], templates=[template("t", ("anything", ["1", "2"]))])]
    found = toys.registry.verify_refs(specs, check_arity=lambda name: (0, 99))
    assert [v.code for v in found] == ["unknown_reply_family"]


def test_the_arity_error_wins_over_the_violations_found_before_it(toys):
    specs = [spec("a", [task_kind("k", "ghost", "x")], templates=[template("t", ("turn-posted", []))])]
    with pytest.raises(RegistryError) as e:
        toys.registry.verify_refs(specs)
    assert code_of(e) == "arity_unbound"


# ---- export ---------------------------------------------------------------------------------------------------------

def test_export_renders_one_schema_file_per_family_and_version_and_an_index(toys):
    class Thing2(Record):
        FAMILY = "thing"
        VERSION = 2
        kind: Literal["thing"] = "thing"
        schema_version: int = 2
        label: str = ""

    toys.registry.register(Thing2)
    files = export.render(toys.registry)
    assert sorted(files) == ["doc.v1.json", "index.json", "pair.v1.json", "thing.v1.json", "thing.v2.json"]
    index = json.loads(files["index.json"])
    assert index == {"doc": {"1": ["doc"]}, "pair": {"1": ["alpha", "beta", "gamma"]}, "thing": {"1": ["thing"], "2": ["thing"]}}
    assert list(index) == ["doc", "pair", "thing"]
    for name, text in files.items():
        assert text.endswith("}\n") and not text.endswith("\n\n")
        assert json.loads(text) is not None
    assert json.loads(files["thing.v2.json"])["properties"]["label"]["type"] == "string"
    assert json.loads(files["thing.v1.json"]) == toys.registry.json_schema("thing", 1)


def test_the_index_lists_versions_in_number_order_and_kinds_in_registration_order():
    reg = ModelRegistry()
    for version in (2, 10, 1):
        reg.register(fresh_class("fam", ["zeta", "alpha"] if version == 10 else ["zeta"], version=version))
    reg.register(fresh_class("fam", ["mid"], version=2))
    reg.register(fresh_class("aaa", ["b", "a"], version=1))
    text = export.render(reg)["index.json"]
    index = json.loads(text)
    assert list(index) == ["aaa", "fam"]
    assert list(index["fam"]) == ["1", "2", "10"]
    assert index["fam"] == {"1": ["zeta"], "2": ["zeta", "mid"], "10": ["zeta", "alpha"]}
    assert index["aaa"] == {"1": ["b", "a"]}


def test_non_ascii_text_in_a_schema_is_written_as_it_is(tmp_path):
    from pydantic import Field as PField
    reg = ModelRegistry()

    class Cafe(Value):
        name: str = PField(default="", description="café — naïve")

    reg.register_payload("cafe", 1, Cafe)
    text = export.render(reg)["cafe.v1.json"]
    assert "café — naïve" in text and "\\u00e9" not in text
    export.write(tmp_path, reg)
    assert "café — naïve" in (tmp_path / "cafe.v1.json").read_text(encoding="utf-8")


def test_export_is_deterministic_sorted_and_indented(toys):
    first, second = export.render(toys.registry), export.render(toys.registry)
    assert first == second
    text = first["thing.v1.json"]
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert text.startswith('{\n  "')
    assert first["index.json"].startswith('{\n  "doc": {\n    "1": [\n      "doc"\n    ]')


def test_export_is_the_same_for_two_registries_built_the_same_way(toys, toy_factory):
    assert export.render(toys.registry) == export.render(toy_factory().registry)


def test_write_then_check_is_clean(toys, tmp_path):
    target = tmp_path / "schemas"
    changed = export.write(target, toys.registry)
    assert sorted(changed) == ["wrote: doc.v1.json", "wrote: index.json", "wrote: pair.v1.json", "wrote: thing.v1.json"]
    assert export.check(target, toys.registry) == []
    assert export.write(target, toys.registry) == []                      # nothing left to do
    assert sorted(p.name for p in target.iterdir()) == ["doc.v1.json", "index.json", "pair.v1.json", "thing.v1.json"]


def test_check_reports_missing_differing_and_stale_files(toys, tmp_path):
    export.write(tmp_path, toys.registry)
    (tmp_path / "pair.v1.json").unlink()
    (tmp_path / "thing.v1.json").write_text("{}\n")
    (tmp_path / "gone.v3.json").write_text("{}\n")
    assert export.check(tmp_path, toys.registry) == ["missing: pair.v1.json", "differs: thing.v1.json", "stale: gone.v3.json"]
    assert export.check(tmp_path / "nowhere", toys.registry) == [
        "missing: doc.v1.json", "missing: pair.v1.json", "missing: thing.v1.json", "missing: index.json"]


def test_check_notices_a_change_to_a_class(toys, tmp_path):
    export.write(tmp_path, toys.registry)

    class Thing3(Record):
        FAMILY = "extra"
        kind: Literal["x"] = "x"

    other = ModelRegistry()
    other.register(toys.Thing)
    other.register(toys.Alpha)
    other.register(toys.Beta)
    other.register_payload("doc", 1, toys.Doc)
    other.register(Thing3)
    problems = export.check(tmp_path, other)
    assert problems == ["missing: extra.v1.json", "differs: index.json"]


def test_write_removes_stale_schema_files_and_leaves_everything_else(toys, tmp_path):
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "generic.json").write_text("{}")
    others = ["notes.txt", "Bad.V1.json", "custom.json", "weird.v.json", "x.v1.json.bak", "v1.json"]
    for name in others:
        (tmp_path / name).write_text("keep me")
    (tmp_path / "old.v1.json").write_text("{}")
    (tmp_path / "old-family.v12.json").write_text("{}")
    changed = export.write(tmp_path, toys.registry)
    assert sorted(c for c in changed if c.startswith("removed")) == ["removed: old-family.v12.json", "removed: old.v1.json"]
    assert not (tmp_path / "old.v1.json").exists() and not (tmp_path / "old-family.v12.json").exists()
    assert (tmp_path / "templates" / "generic.json").exists()
    for name in others:
        assert (tmp_path / name).read_text() == "keep me", name
    assert export.check(tmp_path, toys.registry) == []
    (tmp_path / "gone.v2.json").write_text("{}")
    assert export.check(tmp_path, toys.registry) == ["stale: gone.v2.json"]       # and only schema-shaped files are stale


def test_write_rewrites_a_file_that_differs(toys, tmp_path):
    export.write(tmp_path, toys.registry)
    (tmp_path / "doc.v1.json").write_text("tampered")
    assert export.write(tmp_path, toys.registry) == ["wrote: doc.v1.json"]
    assert export.check(tmp_path, toys.registry) == []


def test_an_empty_registry_exports_an_empty_index(tmp_path):
    assert export.render(ModelRegistry()) == {"index.json": "{}\n"}
    export.write(tmp_path, ModelRegistry())
    assert (tmp_path / "index.json").read_text() == "{}\n"


def test_schema_dir_precedence(monkeypatch, tmp_path):
    monkeypatch.delenv("SUTRA_SCHEMA_DIR", raising=False)
    assert export.schema_dir() == export.DEFAULT_DIR
    assert export.DEFAULT_DIR == Path(export.__file__).resolve().parents[2] / "docs" / "schemas"
    monkeypatch.setenv("SUTRA_SCHEMA_DIR", str(tmp_path / "env"))
    assert export.schema_dir() == tmp_path / "env"
    assert export.schema_dir(str(tmp_path / "arg")) == tmp_path / "arg"
    assert export.schema_dir(tmp_path / "arg") == tmp_path / "arg"


def test_main_writes_then_checks(toys, tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("SUTRA_SCHEMA_DIR", raising=False)
    assert export.main(["--dir", str(tmp_path), "--check"], toys.registry) == 1
    out = capsys.readouterr().out
    assert "schema drift" in out and "missing: index.json" in out and "python -m sutra_app.library.export" in out
    assert export.main(["--dir", str(tmp_path)], toys.registry) == 0
    out = capsys.readouterr().out
    assert "wrote: index.json" in out and "updated (4 files)" in out
    assert export.main(["--dir", str(tmp_path), "--check"], toys.registry) == 0
    assert "up to date (4 files)" in capsys.readouterr().out
    assert export.main(["--dir", str(tmp_path)], toys.registry) == 0
    assert "already up to date" in capsys.readouterr().out


def test_main_uses_the_environment_directory(toys, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SUTRA_SCHEMA_DIR", str(tmp_path / "from-env"))
    assert export.main([], toys.registry) == 0
    assert (tmp_path / "from-env" / "index.json").exists()


def test_main_without_a_registry_loads_the_apps_registry(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(export, "load_registry", lambda: seen.append(1) or ModelRegistry())
    assert export.main(["--dir", str(tmp_path)]) == 0
    assert seen == [1] and (tmp_path / "index.json").exists()


def test_load_registry_returns_the_global_registry_even_before_the_all_module_exists():
    assert export.load_registry() is REGISTRY


def test_load_registry_reraises_a_missing_module_inside_all(monkeypatch):
    def boom(name):
        raise ModuleNotFoundError("No module named 'wire'", name="sutra_app.library.wire")
    monkeypatch.setattr(export, "importlib", SimpleNamespace(import_module=boom))
    with pytest.raises(ModuleNotFoundError, match="wire"):
        export.load_registry()


def test_the_module_runs_from_the_command_line(tmp_path):
    env = {**os.environ, "SUTRA_SCHEMA_DIR": str(tmp_path / "cli"),
           "PYTHONPATH": str(Path(export.__file__).resolve().parents[2])}      # this checkout's code, whatever is installed
    run = lambda *args: subprocess.run([sys.executable, "-m", "sutra_app.library.export", *args], capture_output=True,
                                       text=True, env=env, cwd=str(tmp_path))
    first = run()
    assert first.returncode == 0, first.stderr
    assert (tmp_path / "cli" / "index.json").exists()
    assert run("--check").returncode == 0
    (tmp_path / "cli" / "index.json").write_text("{}")
    broken = run("--check")
    assert broken.returncode == 1 and "differs: index.json" in broken.stdout
    assert run("--bogus").returncode == 2
