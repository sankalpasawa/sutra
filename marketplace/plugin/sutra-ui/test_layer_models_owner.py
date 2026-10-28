"""A4-OWN O1 to O4 (and O8): the spec models, the compile, the rules and the comparison, the store.

The owner's models are data (a spec) made into pydantic classes on a core base; these tests build them from the fixtures in
test_fixtures/models/owner and hold them to the twelve rules (R6 to R12) and to the store's write path."""
import ast
import copy
import json
import time
from pathlib import Path

import pytest

from layer_models import bus, compile as C, owner_rules as OR, registry, rules, spec as SP, store
from layer_models.faults import sentences

HERE = Path(__file__).resolve().parent
FIX = json.loads((HERE / 'test_fixtures' / 'models' / 'owner' / 'specs.json').read_text(encoding='utf-8'))


def F(n, t='text', **k):
    return dict(name=n, label=n.replace('_', ' ').title(), type=t, **k)


def spec(name, base='core:record', fields=None, version=1, **k):
    return dict(name=name, version=version, label=name.replace('_', ' ').title(), base=base, fields=fields or [], **k)


def fix(*names):
    return {'%s/v1' % n: copy.deepcopy(FIX['%s/v1' % n]) for n in names}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv('SUTRA_NATIVE_DEPT_HOME', str(tmp_path / 'departments'))
    monkeypatch.setattr(store, 'MIN_GAP', 0)
    registry.reset()
    yield tmp_path
    registry.reset()


def core():
    return registry.core_map()


def fits(spec_, value):
    return SP.check(SP.ModelSpec, value if spec_ is None else spec_)


# ---- O1: the spec models --------------------------------------------------------------------------------------------------
def good():
    return copy.deepcopy(FIX['client/v1'])


def test_a_spec_fits():
    for k, s in FIX.items():
        assert SP.check(SP.ModelSpec, s) == [], k
    f = {'schema_version': 1, 'rev': 3, 'models': FIX}
    assert SP.check(SP.ModelFile, f) == []


@pytest.mark.parametrize('mutate,sentence', [
    (lambda s: s['fields'].append(dict(F('p'), pattern='^a+$')), 'is not one of slug, code, date'),
    (lambda s: s.__setitem__('fields', [F('f%d' % i) for i in range(41)]), 'more than 40 items'),
    (lambda s: s.__setitem__('links', [dict(name='l%d' % i, label='L', mode='refer', to='x:line/v1') for i in range(11)]), 'more than 10 items'),
    (lambda s: s['fields'].append(F('c', 'choice', choices=['c%d' % i for i in range(13)])), 'more than 12 items'),
    (lambda s: s.__setitem__('name', '1client'), 'does not match'),
    (lambda s: s['fields'].append(dict(name='z', label='Z', type='blob')), 'is not one of text, long_text, whole'),
    (lambda s: s['fields'][0].__setitem__('default', 'x'), 'is not a field here'),
    (lambda s: s.__setitem__('version', 2), 'version 2 builds on version 1'),
])
def test_a_spec_that_does_not_fit_says_why(mutate, sentence):
    s = good()
    mutate(s)
    got = SP.check(SP.ModelSpec, s)
    assert got and any(sentence in g for g in got), got


def test_a_spec_over_64_kb_is_refused_by_the_file():
    big = good()
    big['about'] = 'x' * 300
    big['fields'] = [dict(F('f%d' % i), about='y' * 200) for i in range(40)] + []
    big['links'] = [dict(name='l%d' % i, label='L' * 60, mode='refer', to='x:line/v1') for i in range(10)]
    big['x'] = None
    huge = copy.deepcopy(good())
    huge['fields'] = [dict(F('f'), about='y' * 200)]
    f = {'schema_version': 1, 'rev': 1, 'models': {'client/v1': huge}}
    assert SP.check(SP.ModelFile, f) == []
    # a spec that dumps to more than 64 KB is caught by the file cap before the spec is read
    f['models']['client/v1'] = dict(huge, junk='z' * 70000)
    got = SP.check(SP.ModelFile, f)
    assert any('at most 64 KB' in g for g in got), got


def test_a_file_holds_at_most_sixty_models():
    models = {'m%02d/v1' % i: spec('m%02d' % i) for i in range(61)}
    got = SP.check(SP.ModelFile, {'schema_version': 1, 'rev': 0, 'models': models})
    assert any('at most 60 models' in g for g in got), got


def test_the_history_row_answers_to_class():
    row = {'rev': 1, 'at': 'x', 'by': 'the owner', 'op': 'create', 'key': 'x.client/v1', 'says': 'made Client', 'class': 'same', 'spec': {}}
    assert SP.check(SP.HistoryRow, row) == []


# ---- O2: compile ------------------------------------------------------------------------------------------------------------
def build(*names, **extra):
    specs = fix(*names)
    specs.update(extra)
    return C.compile_all(specs, core())


def test_compile_makes_a_real_pydantic_class_on_a_core_base():
    r = build('client')
    cls = r.classes['x.client/v1']
    from layer_models.owner_base import OwnerRecord
    assert issubclass(cls, OwnerRecord) and cls.__module__ == 'layer_models.owner'
    ad = r.adapter('x.client')
    assert '$.id: is missing' in sentences(ad, {'name': 'Asha'})
    assert sentences(ad, {'id': 'c1', 'name': 'Asha', 'tier': 'gold'}) == []
    assert ad.validate_python({'id': 'c1', 'name': 'A', 'zz': 1}).model_extra == {'zz': 1}       # an open base keeps an extra key
    assert any('longer than 80' in s for s in sentences(ad, {'id': 'c1', 'name': 'x' * 81}))


def test_a_child_narrows_and_is_a_kind_of_its_base():
    r = build('client', 'vip_client')
    client, vip = r.classes['x.client/v1'], r.classes['x.vip_client/v1']
    assert issubclass(vip, client) and r.state['x.vip_client/v1'] == 'on'
    assert sentences(r.adapter('x.vip_client'), {'id': 'v', 'name': 'Zed', 'tier': 'silver'}) != []
    assert sentences(r.adapter('x.client'), {'id': 'v', 'name': 'Zed', 'tier': 'gold', 'since': '2026-10-27'}) == []


def test_a_loosening_child_is_found_at_compile():
    loose = spec('loose', 'x:client/v1', [F('tier', 'choice', choices=['gold', 'platinum']), F('name', max_len=500)])
    r = build('client', **{'loose/v1': loose})
    assert r.state['x.loose/v1'] == 'needs_a_look' and 'x.loose/v1' not in r.classes
    sentences_ = [s for _, s in r.faults['x.loose/v1']]
    assert 'tier: adds platinum to the choices' in sentences_
    assert any('name: allows more than 80' in s for s in sentences_)
    assert r.state['x.client/v1'] == 'on'


def test_nest_and_refer():
    r = build('client', 'line', 'order')
    ad = r.adapter('x.order')
    ok = {'id': 'o1', 'lines': [{'id': 'l1', 'sku': 'A', 'qty': 2}], 'client_id': 'c1'}
    assert sentences(ad, ok) == []
    bad = {'id': 'o1', 'lines': [{'id': 'l1', 'sku': 'A', 'qty': 0}, {'id': 'l1'}], 'client_id': 'C 1'}
    got = sentences(ad, bad)
    assert '$.lines[0].qty: below 1' in got and '$.lines[1].sku: is missing' in got
    assert any(g.startswith('$.client_id: does not match') for g in got)


def test_a_family_dispatches_by_tag():
    r = build('shape', 'circle', 'square')
    ad = r.adapter('x.shape')
    assert sentences(ad, {'id': 's', 'kind': 'circle', 'radius': 2}) == []
    assert sentences(ad, {'id': 's', 'kind': 'zzz'}) == ['$.kind: is not one of circle, square']
    assert sentences(ad, {'id': 's'}) == ['$.kind: is missing']
    assert sentences(ad, {'id': 's', 'kind': 'square'}) == ['$.side: is missing']


def test_off_means_not_offered_and_not_broken():
    specs = fix('client')
    specs['client/v1']['enabled'] = False
    r = C.compile_all(specs, core())
    assert r.state['x.client/v1'] == 'off' and not r.effective('x.client')
    # still validates against it when asked directly
    assert sentences(r.adapters['x.client/v1'], {'id': 'c', 'name': 'A'}) == []
    # and a family leaves an off child out of the union
    specs = fix('shape', 'circle', 'square')
    specs['square/v1']['enabled'] = False
    r = C.compile_all(specs, core())
    assert sentences(r.adapter('x.shape'), {'id': 's', 'kind': 'square'}) == ['$.kind: is not one of circle']


def test_children_follow_their_base_without_losing_their_own_switch():
    specs = fix('client', 'vip_client')
    specs['client/v1']['enabled'] = False
    r = C.compile_all(specs, core())
    assert r.state['x.vip_client/v1'] == 'off'
    assert specs['vip_client/v1'].get('enabled') is not False          # its own switch is untouched
    specs['client/v1']['enabled'] = True
    assert C.compile_all(specs, core()).state['x.vip_client/v1'] == 'on'


def test_a_retired_field_is_never_required_and_still_read():
    s = fix('client')
    s['client/v1']['fields'][2]['retired'] = True
    s['client/v1']['fields'][2]['required'] = True
    ad = C.compile_all(s, core()).adapter('x.client')
    assert sentences(ad, {'id': 'c', 'name': 'A'}) == []
    assert any('longer than 30' in g for g in sentences(ad, {'id': 'c', 'name': 'A', 'phone': 'x' * 31}))


def test_a_rename_keeps_the_old_name():
    s = fix('client')
    s['client/v1']['fields'][2] = dict(F('mobile', max_len=30), aliases=['phone'])
    ad = C.compile_all(s, core()).adapter('x.client')
    assert sentences(ad, {'id': 'c', 'name': 'A', 'phone': '555'}) == []
    assert sentences(ad, {'id': 'c', 'name': 'A', 'mobile': '555'}) == []


def test_no_dynamic_code_in_compile_or_spec():
    banned = {'eval', 'exec', 'compile', '__import__', 'getattr', 'setattr'}
    for name in ('compile.py', 'spec.py'):
        tree = ast.parse((HERE / 'layer_models' / name).read_text(encoding='utf-8'))
        seen = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not (seen & banned), (name, seen & banned)


def test_compile_of_sixty_models_of_forty_fields_is_under_150_ms():
    big = {'m%02d/v1' % i: spec('m%02d' % i, fields=[F('f%d' % j, max_len=50) for j in range(40)]) for i in range(60)}
    C.compile_all(big, core())                                                  # warm the imports
    best = min(_timed(lambda: C.compile_all(big, core())) for _ in range(5))
    assert best < 0.150, best


def _timed(fn):
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t


def test_an_unchanged_model_is_reused_not_rebuilt():
    specs = fix('client', 'vip_client', 'line')
    first = C.compile_all(specs, core())
    specs['line/v1']['label'] = 'Order line'
    second = C.compile_all(specs, core(), reuse=first)
    assert second.classes['x.client/v1'] is first.classes['x.client/v1']
    assert second.classes['x.vip_client/v1'] is first.classes['x.vip_client/v1']
    assert second.classes['x.line/v1'] is not first.classes['x.line/v1']


def test_a_registry_is_immutable():
    r = build('client')
    with pytest.raises(AttributeError):
        r.state = {}
    with pytest.raises(TypeError):
        r.classes['x.y'] = int


# ---- O3: the rules ----------------------------------------------------------------------------------------------------------
def codes(specs, key):
    return {c for c, _ in OR.check(specs, core()).get(key, [])}


def sentence_of(specs, key, code):
    return next(s for c, s in OR.check(specs, core())[key] if c == code)


def test_name_taken_and_name_reserved():
    specs = fix('client')
    got = OR.names(spec('client'), specs, creating=True)
    assert ('NAME_TAKEN', 'a model called Client is already there') in got
    assert ('NAME_RESERVED', 'that name belongs to the app') in OR.names(spec('identity_note'))
    assert ('NAME_RESERVED', 'that name belongs to the app') in OR.names(spec('copy'))


def test_base_unknown():
    specs = fix('client')
    specs['a/v1'] = spec('a', 'core:identity.ask')
    specs['b/v1'] = spec('b', 'x:nothing/v1')
    assert sentence_of(specs, 'x.a/v1', 'BASE_UNKNOWN') == 'Ask cannot be built on'
    assert codes(specs, 'x.b/v1') == {'BASE_UNKNOWN'}


def test_base_off_at_a_save_and_core_locked():
    specs = fix('client', 'vip_client')
    specs['client/v1']['enabled'] = False
    assert OR.base_off(specs, 'vip_client/v1') == [('BASE_OFF', 'Client is off; turn it on first')]
    assert 'x.vip_client/v1' not in OR.check(specs, core())                  # at a load, a child just follows its base
    (code, s), = OR.core_locked('core:record')
    assert code == 'CORE_LOCKED' and s == 'Record is part of the app and cannot be changed'
    assert OR.core_locked('x.client') == []


def test_loosens_base_names_the_field():
    loose = spec('loose', 'x:client/v1', [F('tier', 'choice', choices=['gold', 'platinum'])])
    r = build('client', **{'loose/v1': loose})
    assert ('LOOSENS_BASE', 'tier: adds platinum to the choices') in r.faults['x.loose/v1']


def test_field_name_type_fixed_and_dropped():
    s = spec('thing', fields=[F('json'), F('class'), F('model_dump')])
    assert {c for c, _ in OR.names(s)} == {'FIELD_NAME'}
    assert ('FIELD_NAME', 'json is a name the app keeps') in OR.names(s)
    assert ('FIELD_NAME', 'a_b is used twice in Thing') not in OR.names(spec('thing', fields=[F('a_b'), F('c_d')]))
    assert ('FIELD_NAME', 'a is used twice in Thing') in OR.names(spec('thing', fields=[F('a'), F('a')]))
    old = spec('thing', fields=[F('a'), F('b')])
    new = spec('thing', fields=[F('a', 'whole')])
    got = dict(OR.compare_specs(old, new))
    assert got == {'FIELD_TYPE_FIXED': 'a field keeps its type; make a new model', 'FIELD_DROPPED': 'a field is retired, never removed'}
    assert OR.compare_specs(old, spec('thing', fields=[F('a'), dict(F('c'), aliases=['b'])])) == []        # a rename is no drop


def test_cycle_and_too_deep():
    a = spec('order', links=[dict(name='l', label='L', mode='nest', to='x:line/v1')])
    b = spec('line', links=[dict(name='o', label='O', mode='nest', to='x:order/v1')])
    got = OR.check({'order/v1': a, 'line/v1': b}, core())
    assert any(c == 'CYCLE' and s == 'Order, Line, Order: a circle' for k in got for c, s in got[k]), got
    chain = {}
    for i in range(5):
        chain['m%d/v1' % i] = spec('m%d' % i, links=[dict(name='n', label='N', mode='nest', to='x:m%d/v1' % (i + 1))] if i < 4 else None)
    got = OR.check(chain, core())
    assert any(c == 'TOO_DEEP' for k in got for c, _ in got[k])
    ok = {k: v for k, v in chain.items() if k != 'm4/v1'}
    ok['m3/v1'] = spec('m3')
    assert OR.check(ok, core()) == {}


def test_link_target():
    specs = fix('client')
    specs['t/v1'] = spec('t', links=[dict(name='x', label='X', mode='refer', to='x:nothing/v1')])
    specs['u/v1'] = spec('u', links=[dict(name='x', label='X', mode='nest', to='core:identity.ask')])
    specs['f/v1'] = spec('f', abstract=True)
    specs['w/v1'] = spec('w', links=[dict(name='x', label='X', mode='nest', to='x:f/v1')])
    assert codes(specs, 'x.t/v1') == codes(specs, 'x.u/v1') == codes(specs, 'x.w/v1') == {'LINK_TARGET'}
    assert sentence_of(specs, 'x.u/v1', 'LINK_TARGET') == 'Ask cannot be held by U'
    assert sentence_of(specs, 'x.w/v1', 'LINK_TARGET') == 'F has nothing built on it yet'
    # a new link to a model that is off is refused at a save; one that was there is only reported
    off = fix('client')
    off['client/v1']['enabled'] = False
    new = spec('t', links=[dict(name='x', label='X', mode='refer', to='x:client/v1')])
    assert OR.new_link_faults(None, new, off) == [('LINK_TARGET', 'Client is off')]
    assert OR.new_link_faults(new, new, off) == []


def test_discriminator():
    specs = fix('shape', 'circle', 'square')
    assert OR.check(specs, core()) == {}
    specs['square/v1']['fields'][0]['choices'] = ['circle']
    got = OR.check(specs, core())['x.shape/v1']
    assert ('DISCRIMINATOR', 'Circle and Square both say kind is circle') in got
    specs['square/v1']['fields'] = [F('side', 'number')]
    assert ('DISCRIMINATOR', 'Square has no one-value kind') in OR.check(specs, core())['x.shape/v1']


def test_version_parent():
    v2 = spec('client', version=2, fields=[], parent='x:client/v1')
    specs = fix('client')
    assert OR.check(dict(specs, **{'client/v2': v2}), core()) == {}
    assert codes({'client/v2': v2}, 'x.client/v2') == {'VERSION_PARENT'}
    assert sentence_of({'client/v2': v2}, 'x.client/v2', 'VERSION_PARENT') == 'there is no version 1 to build version 2 on'


def test_too_big_and_too_many():
    s = spec('thing', fields=[F('f%d' % i) for i in range(41)])
    got = {c for c, _ in OR.check({'thing/v1': s}, core())['x.thing/v1']}
    assert 'TOO_MANY' in got
    s = spec('thing')
    s['about'] = 'x' * 70000
    assert 'TOO_BIG' in {c for c, _ in OR.check({'thing/v1': s}, core())['x.thing/v1']}


def test_r10_a_new_version_is_a_child_of_the_last():
    v1 = fix('client')['client/v1']
    v2 = spec('client', version=2, parent='x:client/v1', fields=[F('name', max_len=40, min_len=1, required=True), F('email', max_len=60)])
    r = C.compile_all({'client/v1': v1, 'client/v2': v2}, core())
    assert issubclass(r.classes['x.client/v2'], r.classes['x.client/v1'])
    assert r.resolve('x.client') == 'x.client/v2' and r.resolve('x.client/v1') == 'x.client/v1'
    bad = dict(v2, fields=[F('name', max_len=120, min_len=1, required=True)])
    r = C.compile_all({'client/v1': v1, 'client/v2': bad}, core())
    assert ('LOOSENS_BASE', 'name: allows more than 80 characters') in r.faults['x.client/v2']


def test_r10_a_change_in_place_that_loosens_is_not_in_place(home):
    store.save(fix('client')['client/v1'])
    wider = fix('client')['client/v1']
    wider['fields'][0]['max_len'] = 120
    r = store.save(wider, 1)
    assert isinstance(r, store.Pending) and r['class'] == 'widens'


def test_r11_names_and_vocabulary():
    for n in ('model_dump', 'json', 'class'):
        assert OR.names(spec('thing', fields=[F(n)])), n
    for n in ('__x', 'Name'):
        assert SP.check(SP.ModelSpec, spec('thing', fields=[dict(name=n, label='N', type='text')])), n
    assert SP.check(SP.ModelSpec, spec('thing', fields=[dict(F('a'), pattern='[a-z]+')]))


def test_r12_the_core_is_not_the_owners():
    assert OR.base_ok(spec('a', 'core:identity.ask'), {}, core()) == [('BASE_UNKNOWN', 'Ask cannot be built on')]
    assert OR.base_ok(spec('a', 'core:record'), {}, core()) == []
    assert OR.core_locked('core:record')


# ---- classification (A4.6.3) ------------------------------------------------------------------------------------------------
def classify(old_spec, new_spec, extra=None):
    specs = dict(extra or {})
    a = C.compile_all(dict(specs, **{'t/v1': old_spec}), core())
    b = C.compile_all(dict(specs, **{'t/v1': new_spec}), core())
    return OR.classify(a.classes['x.t/v1'], b.classes['x.t/v1'])


def base_spec(**k):
    return spec('t', fields=[F('name', max_len=80, min_len=1, required=True), F('tier', 'choice', choices=['gold', 'silver']),
                             F('note', max_len=40)], **k)


def edit(**by_field):
    s = base_spec()
    for f in s['fields']:
        f.update(by_field.get(f['name'], {}))
    return s


def test_classification_table():
    old = base_spec()
    assert classify(old, dict(old, label='Thing again')) == 'same'
    assert classify(old, edit(note={'required': True})) == 'tightens'
    assert classify(old, edit(note={'max_len': 20})) == 'tightens'
    assert classify(old, edit(tier={'choices': ['gold']})) == 'tightens'
    assert classify(old, edit(name={'max_len': 120})) == 'widens'
    assert classify(old, edit(tier={'choices': ['gold', 'silver', 'bronze']})) == 'widens'
    assert classify(old, edit(name={'required': False})) == 'widens'
    assert classify(old, edit(note={'pattern': 'slug'})) == 'tightens'
    assert classify(old, edit(name={'max_len': 120}, note={'max_len': 20})) == 'mixed'
    added_optional = dict(old, fields=old['fields'] + [F('extra', max_len=10)])
    assert classify(old, added_optional) in ('same', 'tightens')            # an open model already let the key in
    added_required = dict(old, fields=old['fields'] + [F('extra', max_len=10, required=True)])
    assert classify(old, added_required) == 'tightens'
    retired_required = edit(name={'retired': True})
    assert classify(old, retired_required) == 'widens'
    retired_optional = edit(note={'retired': True})
    assert classify(old, retired_optional) == 'same'


# ---- O4: the store ----------------------------------------------------------------------------------------------------------
def make(name='client'):
    return store.save(fix(name)['%s/v1' % name])


def test_a_save_writes_history_and_bumps_the_bus(home):
    before = bus.revision()
    r = make()
    assert r == {'ok': True, 'rev': 1, 'class': 'same', 'key': 'x.client/v1'}
    assert bus.revision() == before + 1 and 'x.client' in bus.changed_since(before)
    rows = store.history()
    assert rows[-1]['op'] == 'create' and rows[-1]['says'] == 'made Client' and rows[-1]['spec']['name'] == 'client'
    assert SP.check(SP.HistoryRow, rows[-1]) == []
    assert registry.current().state['x.client/v1'] == 'on'
    doc = json.loads((store._paths()[0]).read_text())
    assert doc['rev'] == 1 and SP.check(SP.ModelFile, doc) == []


def test_a_stale_rev_is_refused(home):
    make()
    s = fix('client')['client/v1']
    s['about'] = 'a'
    with pytest.raises(store.ModelFault) as e:
        store.save(s, 0)
    assert e.value.code == 'STALE_REV' and e.value.faults == ['something changed since you looked; reload']
    assert store.save(s, 1)['rev'] == 2


def test_a_tightening_applies_and_a_widening_waits(home):
    make()
    tight = fix('client')['client/v1']
    tight['fields'][0]['max_len'] = 40
    assert store.save(tight, 1)['class'] == 'tightens'
    wide = fix('client')['client/v1']
    wide['fields'][0]['max_len'] = 120
    r = store.save(wide, 2)
    assert isinstance(r, store.Pending) and r['says'] == 'let name run to 120 characters'
    on_disk = json.loads(store._paths()[0].read_text())
    assert on_disk['models']['client/v1']['fields'][0]['max_len'] == 40 and on_disk['rev'] == 2
    rows = json.loads(store._paths()[2].read_text())
    assert rows[0]['id'] == r['pending_id'] and rows[0]['base_rev'] == 2 and rows[0]['spec']['fields'][0]['max_len'] == 120
    assert rows[0]['id'].startswith('p-') and len(rows[0]['id']) == 10


def test_the_stamp_applies_and_no_drops(home):
    make()
    wide = fix('client')['client/v1']
    wide['fields'][0]['max_len'] = 120
    r = store.save(wide, 1)
    out = store.apply_pending(r['pending_id'], True)
    assert out['rev'] == 2 and registry.current().specs['client/v1']['fields'][0]['max_len'] == 120
    assert store.history()[-1]['op'] == 'stamp' and store.pending() == []
    wide['fields'][0]['max_len'] = 200
    r = store.save(wide, 2)
    assert store.apply_pending(r['pending_id'], False) == {'ok': True, 'dropped': True}
    assert registry.current().specs['client/v1']['fields'][0]['max_len'] == 120 and store.rev() == 2 and store.pending() == []


def test_a_stale_pending_change_is_dropped_and_says_so(home):
    make()
    wide = fix('client')['client/v1']
    wide['fields'][0]['max_len'] = 120
    r = store.save(wide, 1)
    other = fix('client')['client/v1']
    other['about'] = 'moved on'
    store.save(other, 1)
    with pytest.raises(store.ModelFault) as e:
        store.apply_pending(r['pending_id'], True)
    assert e.value.code == 'STALE_REV' and 'dropped' in e.value.faults[0]
    assert store.pending() == []
    with pytest.raises(store.ModelFault) as e:
        store.apply_pending('p-00000000', True)
    assert e.value.code == 'UNKNOWN_PENDING' and e.value.status == 404


def test_undo_is_direct(home):
    make()
    s = fix('client')['client/v1']
    s['fields'].append(F('email', max_len=60))
    store.save(s, 1)
    assert 'email' in [f['name'] for f in registry.current().specs['client/v1']['fields']]
    out = store.undo('x.client', 2)
    assert out['class'] == 'same'
    assert 'email' not in [f['name'] for f in registry.current().specs['client/v1']['fields']]
    first = store.undo('x.client', 3)                       # the undo itself is a change, undone the same way
    assert 'email' in [f['name'] for f in registry.current().specs['client/v1']['fields']] and first['rev'] == 4


def test_revert_goes_by_comparison(home):
    make()
    tight = fix('client')['client/v1']
    tight['fields'][0]['max_len'] = 40
    store.save(tight, 1)
    r = store.revert('x.client', 1, 2)                       # back to the looser one: lets in more
    assert isinstance(r, store.Pending)
    store.apply_pending(r['pending_id'], False)
    wide = fix('client')['client/v1']
    wide['fields'][0]['max_len'] = 120
    store.apply_pending(store.save(wide, 2)['pending_id'], True)           # rev 3
    back = store.revert('x.client', 2, 3)                    # to the 40 one: tighter, direct
    assert back['class'] == 'tightens' and registry.current().specs['client/v1']['fields'][0]['max_len'] == 40
    with pytest.raises(store.ModelFault) as e:
        store.revert('x.client', 99, 4)
    assert e.value.code == 'UNKNOWN_MODEL'


def test_nothing_is_deleted(home):
    make()
    store.set_enabled('x.client', False, 1)
    assert registry.current().state['x.client/v1'] == 'off' and 'client/v1' in json.loads(store._paths()[0].read_text())['models']
    s = fix('client')['client/v1']
    s['fields'][2]['retired'] = True
    s['enabled'] = False
    store.save(s, 2)
    assert [f['name'] for f in store.load()['models']['client/v1']['fields']] == ['name', 'tier', 'phone']
    assert [r['op'] for r in store.history()] == ['create', 'disable', 'edit']
    gone = fix('client')['client/v1']
    gone['fields'] = gone['fields'][:2]
    with pytest.raises(store.ModelFault) as e:
        store.save(gone, 3)
    assert e.value.code == 'FIELD_DROPPED'


def test_turning_on_a_child_while_its_base_is_off_is_base_off(home):
    make()
    make('vip_client')
    store.set_enabled('x.vip_client', False, 2)
    store.set_enabled('x.client', False, 3)
    with pytest.raises(store.ModelFault) as e:
        store.set_enabled('x.vip_client', True, 4)
    assert e.value.code == 'BASE_OFF' and e.value.faults == ['Client is off; turn it on first']


def test_a_changed_base_is_checked_again(home, monkeypatch):
    from typing import Annotated, Any
    from layer_models.base import Open
    from layer_models.types import Enum, Str
    from layer_models.owner_base import OwnerRecord

    class Rec1(Open):
        __abstract__ = True
        id: Annotated[str, Str(40, 1, word=True)]
        tier: Annotated[Any, Enum('gold', 'silver')] = None

    class Rec2(Open):
        __abstract__ = True
        id: Annotated[str, Str(40, 1, word=True)]
        tier: Annotated[Any, Enum('gold')] = None

    class Rec3(Open):
        __abstract__ = True
        id: Annotated[str, Str(40, 1, word=True)]
        tier: Annotated[Any, Enum('gold', 'silver')] = None
        extra: Annotated[str, Str(10)] = None

    monkeypatch.setattr(registry, 'core_map', lambda: {'core:record': Rec1})
    s = spec('thing', fields=[F('tier', 'choice', choices=['gold', 'silver'])])
    store.save(s)
    sha1 = store.load()['models']['thing/v1']['base_sha']
    assert sha1 and registry.current().state['x.thing/v1'] == 'on'
    monkeypatch.setattr(registry, 'core_map', lambda: {'core:record': Rec3})       # additive: it still fits
    store.reload()
    assert store.history()[-1]['op'] == 'rebase' and store.load()['models']['thing/v1']['base_sha'] != sha1
    monkeypatch.setattr(registry, 'core_map', lambda: {'core:record': Rec2})       # tighter: the child now loosens
    store.reload()
    reg = registry.current()
    assert reg.state['x.thing/v1'] == 'needs_a_look' and 'tier' in reg.why['x.thing/v1']
    assert store.history()[-1]['op'] == 'base_changed'
    assert 'thing/v1' in store.load()['models']                                     # nothing is deleted
    n = len(store.history())
    store.reload()
    assert len(store.history()) == n                                                # said once


def test_a_bad_file_is_kept_and_marked(home):
    make()
    p = store._paths()[0]
    doc = json.loads(p.read_text())
    doc['models']['broken/v1'] = {'name': 'broken', 'version': 1, 'label': 'Broken', 'base': 'core:record',
                                  'fields': [{'name': 'a', 'label': 'A', 'type': 'blob'}]}
    p.write_text(json.dumps(doc))
    before = p.read_text()
    reg = store.reload()
    assert reg.state['x.broken/v1'] == 'needs_a_look' and 'type' in reg.why['x.broken/v1']
    assert reg.state['x.client/v1'] == 'on'
    assert p.read_text() == before                                                   # a load rewrites nothing
    p.write_text('{not json')
    reg = store.reload()
    assert reg.state == {} and p.read_text() == '{not json'
    with pytest.raises(store.ModelFault) as e:
        store.save(fix('client')['client/v1'])
    assert e.value.code == 'BAD_FILE' and p.read_text() == '{not json'


def test_history_rolls_at_5_mb(home, monkeypatch):
    monkeypatch.setattr(store, 'HISTORY_MAX', 2000)
    make()
    s = fix('client')['client/v1']
    for i in range(6):
        s['about'] = 'edit %d ' % i + 'x' * 100
        store.save(s)
    h = store._paths()[1]
    assert h.with_name('history.1.jsonl').exists() and h.exists()
    assert len(store.history()) >= 2


def test_one_write_a_second(home, monkeypatch):
    monkeypatch.setattr(store, 'MIN_GAP', 1.0)
    t = [100.0]
    monkeypatch.setattr(store, '_clock', lambda: t[0])
    store._LAST_WRITE[0] = 0.0
    make()
    s = fix('client')['client/v1']
    s['about'] = 'a'
    with pytest.raises(store.ModelFault) as e:
        store.save(s)
    assert e.value.code == 'SLOW_DOWN' and e.value.status == 429
    t[0] += 1.5
    assert store.save(s)['ok']


def test_a_model_called_like_one_that_exists_is_taken(home):
    make()
    with pytest.raises(store.ModelFault) as e:
        store.save(dict(spec('client'), label='Other'), create=True)
    assert e.value.code == 'NAME_TAKEN'
    with pytest.raises(store.ModelFault) as e:
        store.save(spec('identity_x'))
    assert e.value.code == 'NAME_RESERVED'


def test_a_save_that_loosens_below_its_base_names_the_field(home):
    make()
    with pytest.raises(store.ModelFault) as e:
        store.save(spec('loose', 'x:client/v1', [F('tier', 'choice', choices=['gold', 'platinum'])]))
    assert e.value.code == 'LOOSENS_BASE' and 'tier: adds platinum to the choices' in e.value.faults
    assert 'loose/v1' not in store.load()['models']


def test_every_applied_change_leaves_a_row_in_roots_runs(home, monkeypatch):
    import website_dept as W
    d = W.home() / 'org-root'
    d.mkdir(parents=True)
    (d / 'dept.json').write_text(json.dumps({'kind': 'root', 'ref': 'org-root', 'name': 'Org Root'}))
    make()
    s = fix('client')['client/v1']
    s['fields'].append(F('email', max_len=60))
    store.save(s, 1)
    s['fields'][0]['max_len'] = 120
    store.save(s, 2)
    rows = [r['what'] for r in W.runs('org-root')]
    assert 'the owner changed Client: made Client' in rows
    assert 'the owner changed Client: added the field email' in rows
    assert "the owner asked to let name run to 120 characters for Client; it waits for the owner's stamp" in rows
    assert all(r['engine'] == 'Root' and r['system'] for r in W.runs('org-root'))
