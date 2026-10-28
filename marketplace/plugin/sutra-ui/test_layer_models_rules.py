"""A4-CORE C5: the class rules R1 to R6 and R10's compare, on classes."""
from typing import Annotated, Any, Union

import pytest
from pydantic import TypeAdapter

from layer_models import registry, rules
from layer_models.base import Closed, Mixin, Open
from layer_models.faults import sentences
from layer_models.types import AnyOf, Bool, Enum, Int, Items, Str


def T(n, m=0, **k):
    return Annotated[str, Str(n, m, **k)]


def E(*v):
    return Annotated[Any, Enum(*v)]


def L(of, mx=None, mn=0, uq=False):
    return Annotated[list[of], Items(mx, mn, uq)]


def NL(of):
    return Annotated[Union[of, None], AnyOf()]


class Client(Open):
    __def__ = 'x.client'
    name: T(80, 1)
    tier: E('gold', 'silver', 'bronze') = None
    code: T(10, 1, pattern=r'^[a-z]+$') = None
    note: T(40, 0, say=True) = None
    prompt: T(40, 1, field={'multiline': False}) = None
    qty: Annotated[int, Int(1, 9)] = None
    tags: L(T(8), 5, 1, True) = None
    owner: T(20, 1) = None


class Vip(Client):
    __def__ = 'x.vip'
    tier: E('gold') = None                                   # narrower
    name: T(40, 1)                                           # shorter
    since: T(10) = None                                      # new


def child(base, **fields):
    """A throw-away child of `base` with the given annotations; __def__ None so the class check does not fire."""
    ns = {'__annotations__': {k: v[0] for k, v in fields.items()}, '__def__': None}
    ns.update({k: v[1] for k, v in fields.items() if len(v) > 1})
    return type('Loose', (base,), ns)


# ---- R1 ------------------------------------------------------------------------------------------------------------------
def test_r1_a_child_keeps_every_field_of_its_base(monkeypatch):
    assert rules.child_faults(Vip, Client) == []
    trimmed = {k: v for k, v in Vip.model_fields.items() if k != 'name'}
    monkeypatch.setattr(Vip, '__pydantic_fields__', trimmed)
    assert 'name: dropped' in rules.child_faults(Vip, Client)
    assert rules.child_faults(Open, Client) == ['Open is not a kind of Client']


def test_check_class_refuses_a_definition_that_loosens():
    with pytest.raises(TypeError, match='name: allows more than 80 characters'):
        class Bad(Client):
            __def__ = 'x.bad'
            name: T(500, 1)


# ---- R2 ------------------------------------------------------------------------------------------------------------------
LOOSE = [
    ('a longer maximum', {'name': (T(500, 1),)}, 'name: allows more than 80 characters'),
    ('a shorter minimum', {'name': (T(80, 0),)}, 'name: allows fewer than 1 characters'),
    ('a dropped pattern', {'code': (T(10, 1), None)}, 'code: drops the pattern'),
    ('a changed pattern', {'code': (T(10, 1, pattern=r'^[a-z0-9]+$'), None)}, 'code: changes the pattern'),
    ('a dropped say', {'note': (T(40), None)}, 'note: drops the control-character rule'),
    ('a dropped prompt-field rule', {'prompt': (T(40, 1), None)}, 'prompt: drops the prompt-field rule'),
    ('a wider range at the low end', {'qty': (Annotated[int, Int(0, 9)], None)}, 'qty: allows below 1'),
    ('a wider range at the high end', {'qty': (Annotated[int, Int(1, 10)], None)}, 'qty: allows above 9'),
    ('an open range', {'qty': (Annotated[int, Int()], None)}, 'qty: allows below 1'),
    ('a new choice', {'tier': (E('gold', 'platinum'), None)}, 'tier: adds platinum to the choices'),
    ('a longer list', {'tags': (L(T(8), 9, 1, True), None)}, 'tags: allows more than 5 items'),
    ('an emptier list', {'tags': (L(T(8), 5, 0, True), None)}, 'tags: allows fewer than 1 items'),
    ('a dropped unique', {'tags': (L(T(8), 5, 1, False), None)}, 'tags: drops the one-of-each rule'),
    ('a looser item', {'tags': (L(T(80), 5, 1, True), None)}, 'tags[]: allows more than 8 characters'),
    ('required made optional', {'name': (T(80, 1), None)}, 'name: was required and is now optional'),
    ('never-empty made nullable', {'owner': (NL(T(20, 1)), None)}, 'owner: was never empty and now may be'),
    ('a list made a text', {'tags': (T(8), None)}, 'tags: is no longer a list'),
    ('a text made a number', {'name': (Annotated[int, Int()],)}, 'name: changes the kind of value'),
]


@pytest.mark.parametrize('what,fields,sentence', LOOSE, ids=[x[0] for x in LOOSE])
def test_r2_one_loosening_each(what, fields, sentence):
    Loose = child(Client, **fields)
    assert sentence in rules.child_faults(Loose, Client), rules.child_faults(Loose, Client)


class Order(Open):
    __def__ = 'x.order'
    client: Client
    lines: L(Client, 5, 1)


def test_r2_a_nested_model_that_is_not_a_child_and_a_closed_base_made_open():
    class Stranger(Open):
        name: T(80, 1)
    Loose = child(Order, client=(Stranger,))
    assert 'client: is not a kind of Client' in rules.child_faults(Loose, Order)

    class Fixed(Closed):
        __def__ = 'x.fixed'
        a: T(5) = None
    Wide = type('Wide', (Fixed,), {'__annotations__': {}, '__def__': None, 'model_config': {'extra': 'allow'}})
    assert any('allows keys the base refuses' in f for f in rules.child_faults(Wide, Fixed))
    Tight = type('Tight', (Fixed,), {'__annotations__': {}, '__def__': None})
    assert rules.child_faults(Tight, Fixed) == []             # inherits the closed config


def test_r2_a_tighter_child_is_allowed():
    Tight = child(Client, name=(T(10, 2),), tier=(E('gold'), None), qty=(Annotated[int, Int(2, 5)], None),
                  tags=(L(T(4), 2, 2, True), None), code=(T(5, 1, pattern=r'^[a-z]+$'), None))
    assert rules.child_faults(Tight, Client) == []
    assert rules.child_faults(Vip, Client) == []
    Nested = child(Order, client=(Vip,))
    assert rules.child_faults(Nested, Order) == []
    # a nullable base accepts a child that is not nullable, and a child of a Num base may be an Int
    class Nb(Open):
        a: NL(T(5)) = None
        n: Annotated[float, __import__('layer_models.types', fromlist=['Num']).Num(0, 9)] = None
    class Nc(Nb):
        a: T(3) = None
        n: Annotated[int, Int(1, 5)] = None
    assert rules.child_faults(Nc, Nb) == []


# ---- R3 ------------------------------------------------------------------------------------------------------------------
def test_r3_a_value_the_child_takes_the_base_takes():
    assert rules.substitutable(Vip, Client, n=200, seed=1) == []
    assert rules.substitutable(Client, Client, n=100, seed=2) == []


def test_r3_catches_what_a_blind_narrows_lets_through(monkeypatch):
    Loose = child(Client, name=(T(500, 1),), tier=(E('gold', 'platinum'), None))
    assert rules.child_faults(Loose, Client)
    monkeypatch.setattr(rules, 'narrows', lambda *a: [])      # a bug in R2 ...
    assert rules.child_faults(Loose, Client) == []
    got = rules.substitutable(Loose, Client, n=300, seed=3)    # ... is found by running values
    assert got and 'Client refuses' in got[0]


def test_r3_an_abstract_base_is_checked_through_a_concrete_stand_in():
    class Rec(Open):
        __abstract__ = True
        id: T(10, 1)

    class Kid(Rec):
        __abstract__ = False
        __def__ = 'x.kid'
        id: T(5, 1)
    assert rules.substitutable(Kid, Rec, n=50) == []


# ---- R5 ------------------------------------------------------------------------------------------------------------------
class Identified(Mixin):
    __abstract__ = True
    id: T(40, 1)


class OtherIdentified(Mixin):
    __abstract__ = True
    id: T(64, 1)


class Stamped(Mixin):
    __abstract__ = True
    at: T(40) = None


def test_r5_two_bases_that_disagree_on_a_field_are_refused():
    with pytest.raises(TypeError, match='id: the bases disagree'):
        class Both(Identified, OtherIdentified):
            pass

    class Fine(Identified, Stamped):                           # no shared field
        pass
    assert set(Fine.model_fields) == {'id', 'at'}

    class SameId(Mixin):
        __abstract__ = True
        id: T(40, 1)

    class Twin(Identified, SameId):                            # the same type twice is no conflict
        pass
    assert 'id' in Twin.model_fields

    class Settled(Identified, OtherIdentified):                # the class says which one it means
        id: T(30, 1)
    assert rules.child_faults(Settled, Identified) == [] and rules.child_faults(Settled, OtherIdentified) == []


def test_r5_a_mixin_is_never_a_definition():
    with pytest.raises(TypeError, match='mixin'):
        class Bad(Mixin):
            __def__ = 'x.bad'
            a: T(3) = None
    with pytest.raises(TypeError, match='abstract'):
        Identified(id='a')


# ---- R6 ------------------------------------------------------------------------------------------------------------------
def test_r6_a_nest_cycle_is_found_and_named():
    assert rules.nest_cycle({'order': ['line', 'client'], 'line': ['order'], 'client': []}) == ['order', 'line', 'order']
    assert rules.nest_cycle({'a': ['b'], 'b': ['c'], 'c': ['a']}) == ['a', 'b', 'c', 'a']
    assert rules.nest_cycle({'a': ['a']}) == ['a', 'a']
    assert rules.nest_cycle({'order': ['line', 'client'], 'line': [], 'client': ['line']}) is None
    assert rules.nest_cycle({'a': ['unknown']}) is None
    assert rules.nest_cycle({}) is None


def test_r6_depth_counts_the_models_on_the_longest_path():
    assert rules.nest_depth({}) == 0
    assert rules.nest_depth({'a': []}) == 1
    assert rules.nest_depth({'a': ['b'], 'b': ['c'], 'c': ['d'], 'd': ['e'], 'e': []}) == 5
    assert rules.nest_depth({'order': ['line', 'client'], 'line': [], 'client': ['line']}) == 3
    assert rules.nest_depth({'a': ['b'], 'b': ['a']}) >= 2          # a circle is cut, not followed forever


# ---- R10 -----------------------------------------------------------------------------------------------------------------
def test_compare_table():
    class V1(Open):
        name: T(80, 1)
        qty: Annotated[int, Int(1, 9)] = None

    def v2(**kw):
        ns = {'__annotations__': {k: v[0] for k, v in kw.items()}, '__def__': None}
        ns.update({k: v[1] for k, v in kw.items() if len(v) > 1})
        return type('V2', (Open,), ns)
    same = v2(name=(T(80, 1),), qty=(Annotated[int, Int(1, 9)], None))
    tight = v2(name=(T(40, 1),), qty=(Annotated[int, Int(1, 9)], None))
    wide = v2(name=(T(120, 1),), qty=(Annotated[int, Int(1, 9)], None))
    mixed = v2(name=(T(120, 1),), qty=(Annotated[int, Int(2, 9)], None))
    newreq = v2(name=(T(80, 1),), qty=(Annotated[int, Int(1, 9)], None), extra=(T(5),))
    assert rules.compare(V1, same) == 'same'
    assert rules.compare(V1, tight) == 'tightens'
    assert rules.compare(V1, wide) == 'widens'
    assert rules.compare(V1, mixed) == 'mixed'
    assert rules.compare(V1, newreq) == 'tightens'            # a new required field
    assert rules.compare(V1, v2(name=(T(80, 1),))) == 'widens'   # qty no longer typed

    class C1(Closed):
        a: T(5) = None

    class C2(Closed):
        a: T(5) = None
        b: T(5) = None
    assert rules.compare(C1, C2) == 'widens'                  # a new field on a closed class lets in a key it refused
    assert rules.compare(C1, C1) == 'same'


# ---- the registry --------------------------------------------------------------------------------------------------------
def test_the_adapter_is_built_once(monkeypatch):
    registry.register('x.t', Client)
    registry.register('x.list', Annotated[list[Client], Items(3)])
    assert registry.classes()['x.t'] is Client and 'x.list' in registry.DEF_TYPE
    registry.adapter('x.t')
    registry.adapter('x.list')
    count = []
    orig = TypeAdapter.__init__
    monkeypatch.setattr(TypeAdapter, '__init__', lambda self, *a, **k: (count.append(1), orig(self, *a, **k))[1])
    for _ in range(1000):
        registry.adapter('x.t')
        registry.adapter('x.list')
    assert count == []                                         # already built: no new adapter in 2,000 calls
    registry.register('x.t', Vip)                              # a new registration drops the old adapter
    registry.adapter('x.t')
    for _ in range(1000):
        registry.adapter('x.t')
    assert count == [1]
    assert sentences(registry.adapter('x.t'), {'name': 'a' * 41}) == ['$.name: longer than 40']
    with pytest.raises(KeyError):
        registry.adapter('nobody')
