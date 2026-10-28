"""A4-CORE C2: every constructor of layer_schema against its annotation object: the same verdict, the same sentences, the same
JSON Schema dict."""
import json
import math
from typing import Annotated, Any, Union

import pytest
from pydantic import TypeAdapter

import layer_schema as S
from layer_models.base import Closed
from layer_models.faults import sentences
from layer_models.schema import export
from layer_models.types import (AnyOf, Anything, Bare, Bool, Const, DefRef, Enum, Int, Items, Law, MapOf, Num, Owner, Ref, Str)

#: the 21 values of the proof's differential, and the strings the walker is picky about
KINDS = [None, True, 0, 7, -1, 2.5, 3.0, '', 'x', 'D1', [], [1], {}, {'a': 1}, 'a' * 5000, '\x01', 'a\nb', '{{x}}', 'Return ONLY',
         'abc\n', float('nan')]
STRINGS = ['', 'ab', 'abc', 'ABC', 'a' * 41, 'a b', 'abc\n', 'a\tb', 'a\x7fb', '{{', '}}', 'x}}y', 'Return ONLY', 'tell me. Return ONLY json',
           'line\nbreak', 'ctrl\x01', 'a' * 5000, 'D12', '2026-10-27', 'engine/a-b']
VALUES = KINDS + STRINGS + [-5, 100, 1e9, 0.5, 1.0, ('a', 'b'), ['a', 'a'], ['a', 'b', 'c'], {'ab': 1}, {'AB': 1}, {'ab': 'x', 'cd': 2},
                            [None], [1, 2, 3, 4], [[]], ['a', None]]

# (name, legacy schema, annotation)
GRID = []
for mx, mn in ((10, 0), (40, 1), (3, 3)):
    GRID.append(('text(%d,%d)' % (mx, mn), S.text(mx, mn), Annotated[str, Str(mx, mn)]))
    GRID.append(('say(%d,%d)' % (mx, mn), S.say(mx, mn), Annotated[str, Str(mx, mn, say=True)]))
    for ml in (False, True):
        GRID.append(('field(%d,%d,%s)' % (mx, mn, ml), S.field(mx, mn, ml), Annotated[str, Str(mx, mn, field={'multiline': ml})]))
for pat, mx in ((r'^[a-z]+$', 40), (r'^D[1-9][0-9]*$', 3), (r'^\d{4}-\d\d-\d\d', 40)):
    GRID.append(('word(%s,%d)' % (pat, mx), S.word(pat, mx), Annotated[str, Str(mx, 0, pattern=pat, word=True)]))
GRID.append(('iso()', S.iso(), Annotated[str, Str(40, pattern=r'^\d{4}-\d\d-\d\d', word=True)]))
GRID.append(('text+pattern', dict(S.text(5, 3), pattern='^[a-z]+$'), Annotated[str, Str(5, 3, pattern='^[a-z]+$')]))
for lo, hi in ((None, None), (0, None), (1, 99), (None, 5), (-3, 3)):
    GRID.append(('integer(%s,%s)' % (lo, hi), S.integer(lo, hi), Annotated[int, Int(lo, hi)]))
    GRID.append(('number(%s,%s)' % (lo, hi), S.number(lo, hi), Annotated[float, Num(lo, hi)]))
GRID.append(('boolean()', S.boolean(), Annotated[bool, Bool()]))
GRID.append(('enum str', S.enum('a', 'b', 'c'), Annotated[Any, Enum('a', 'b', 'c')]))
GRID.append(('enum mixed', S.enum(1, 2, True, None, 'x'), Annotated[Any, Enum(1, 2, True, None, 'x')]))
GRID.append(('enum long', S.enum(*[str(i) for i in range(12)]), Annotated[Any, Enum(*[str(i) for i in range(12)])]))
GRID.append(('const str', S.const('conflict'), Annotated[Any, Const('conflict')]))
GRID.append(('const false', S.const(False), Annotated[Any, Const(False)]))
GRID.append(('const 1', S.const(1), Annotated[Any, Const(1)]))
GRID.append(('ANYTHING', S.ANYTHING, Annotated[Any, Anything()]))
GRID.append(('obj({})', S.obj({}), Annotated[dict[str, Any], Bare()]))
for mx, mn, uq in ((None, 0, False), (3, 0, False), (3, 1, True), (None, 2, False), (2, 0, True)):
    GRID.append(('items(%s,%s,%s)' % (mx, mn, uq), S.items(S.text(3), mx, mn, uq), Annotated[list[Annotated[str, Str(3)]], Items(mx, mn, uq)]))
GRID.append(('items of items', S.items(S.items(S.integer(0, 9), 2), 3), Annotated[list[Annotated[list[Annotated[int, Int(0, 9)]], Items(2)]], Items(3)]))
GRID.append(('items(ANYTHING)', S.items(S.ANYTHING, 2), Annotated[list[Annotated[Any, Anything()]], Items(2)]))
GRID.append(('map_of', S.map_of(S.text(3)), Annotated[dict[str, Annotated[str, Str(3)]], MapOf()]))
GRID.append(('map_of keys', S.map_of(S.integer(0, 9), r'^[a-z]+$'), Annotated[dict[str, Annotated[int, Int(0, 9)]], MapOf(r'^[a-z]+$')]))
GRID.append(('nullable', S.nullable(S.text(3)), Annotated[Union[Annotated[str, Str(3)], None], AnyOf()]))
GRID.append(('nullable enum', S.nullable(S.enum('a', 'b')), Annotated[Union[Annotated[Any, Enum('a', 'b')], None], AnyOf()]))
GRID.append(('any_of', S.any_of(S.integer(0), S.boolean()), Annotated[Union[Annotated[int, Int(0)], Annotated[bool, Bool()]], AnyOf()]))
GRID.append(('any_of text int', S.any_of(S.text(3), S.integer(0, 9)), Annotated[Union[Annotated[str, Str(3)], Annotated[int, Int(0, 9)]], AnyOf()]))


def one_field(ann):
    class One(Closed):
        v: ann
    return One


def same(a, b):
    return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)


@pytest.mark.parametrize("name,sch,ann", GRID, ids=[g[0] for g in GRID])
def test_each_constructor_equals_its_annotation(name, sch, ann):
    cls = one_field(ann)
    ad = TypeAdapter(cls)
    for v in VALUES:
        want = S.faults(sch, v)
        got = [s.replace('$.v', '$', 1) for s in sentences(ad, {'v': v})]
        assert got == want, "%s on %r: oracle %s, port %s" % (name, v if not isinstance(v, str) else v[:40], want, got)
    assert same(export(cls)['properties']['v'], sch), "%s: the file differs: %s vs %s" % (name, export(cls)['properties']['v'], sch)


def test_a_bool_is_not_a_whole_number_and_3_0_is():
    ad = TypeAdapter(Annotated[int, Int()])
    assert sentences(ad, True) == ['$: is not a whole number']
    assert sentences(ad, 3.0) == [] and sentences(ad, 3) == []
    assert sentences(ad, 2.5) == ['$: is not a whole number']
    assert sentences(ad, '3') == ['$: is not a whole number']
    nm = TypeAdapter(Annotated[float, Num()])
    assert sentences(nm, True) == ['$: is not a number'] and sentences(nm, 2.5) == []
    assert TypeAdapter(Annotated[Any, Enum(1)]).validate_python(1.0) == 1.0
    assert sentences(TypeAdapter(Annotated[Any, Enum(1, 2)]), True) == ['$: is not one of 1, 2']


def test_a_pattern_is_searched_by_python_re():
    ad = TypeAdapter(Annotated[str, Str(10, pattern=r'^[a-z]+$')])
    assert sentences(ad, 'abc\n') == []                  # G1: Rust's regex would refuse it
    assert sentences(ad, 'ab1') == ['$: does not match ^[a-z]+$']


def test_all_failures_of_one_value_are_reported_together():
    ad = TypeAdapter(Annotated[str, Str(40, 3, pattern=r'^[a-z]+$')])
    assert sentences(ad, 'A') == ['$: shorter than 3', '$: does not match ^[a-z]+$']
    ad = TypeAdapter(Annotated[str, Str(2, 0, say=True)])
    assert sentences(ad, 'abc\x01') == ['$: longer than 2', '$: holds a control character']
    ad = TypeAdapter(Annotated[str, Str(40, 1, field={'multiline': False})])
    assert len(sentences(ad, '{{ Return ONLY\n')) == 3


def test_defref_bare_owner_law_write_their_keywords():
    from layer_models import registry
    body = S.DEFS['name']
    name = Annotated[str, Str(40, 0, pattern=S.NAME_RE, word=True), DefRef('name', body)]

    class Dept(Closed):
        a: Annotated[name, Owner('identity')] = None
        b: Annotated[str, Str(5), Law('fixed')] = None
        c: Annotated[dict[str, Any], Bare()] = None
        d: Annotated[str, Str(5, 0, pattern='^a', word=True), Ref('x.client', Str(5, 0, pattern='^a', word=True))] = None
    got = export(Dept)['properties']
    assert got['a'] == {'$ref': '#/$defs/name', 'x-owner': 'identity'}
    assert got['b'] == dict(S.text(5), **{'x-law': 'fixed'})
    assert got['c'] == {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': True}
    assert got['d']['x-ref'] == 'x.client' and 'minLength' not in got['d']
    assert registry.ALIASES['name'] is body
    with pytest.raises(ValueError):
        Law('maybe')
    # the sentence of a Ref is its Str's own
    ad = TypeAdapter(Dept)
    assert sentences(ad, {'d': 'b'}) == ['$.d: does not match ^a']


def test_bounds_report_the_parameters():
    assert Str(5, 1, pattern='^a', say=True).bounds() == {'max_len': 5, 'min_len': 1, 'pattern': '^a', 'say': True, 'field': None, 'word': False}
    assert Int(1, 9).bounds() == {'minimum': 1, 'maximum': 9} and Enum('a', 'b').bounds() == {'values': ['a', 'b']}
    assert Items(3, 1, True).bounds() == {'max_items': 3, 'min_items': 1, 'unique': True} and MapOf('^a').bounds() == {'keys': '^a'}
    assert Const(2).bounds() == {'value': 2}
