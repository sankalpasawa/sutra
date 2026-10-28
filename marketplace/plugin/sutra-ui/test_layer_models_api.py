"""A4-OWN O5 (and O8): the routes of the owner's models, their read models, and the security rows of A4.5.8."""
import copy
import importlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from layer_models import registry, store

HERE = Path(__file__).resolve().parent
FIX = json.loads((HERE / 'test_fixtures' / 'models' / 'owner' / 'specs.json').read_text(encoding='utf-8'))
BASE = '/api/native/_models'


def fix(name):
    return copy.deepcopy(FIX['%s/v1' % name])


def F(n, t='text', **k):
    return dict(name=n, label=n.replace('_', ' ').title(), type=t, **k)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv('SUTRA_NATIVE_DEPT_HOME', str(tmp_path / 'departments'))
    monkeypatch.setattr(store, 'MIN_GAP', 0)
    registry.reset()
    yield tmp_path
    registry.reset()


@pytest.fixture
def api(home):
    import models_api
    import website_api
    app = FastAPI()
    app.include_router(models_api.router)                     # before website_api, as app.py does
    app.include_router(website_api.router)
    return TestClient(app)


def make(api, name='client', **over):
    r = api.post(BASE, json={'spec': dict(fix(name), **over)})
    assert r.status_code == 200, r.text
    return r.json()


def detail(r):
    return r.json()['detail']


# ---- the routes, each with its success and its errors ---------------------------------------------------------------------
def test_create_then_read_the_list_the_page_the_shape_and_the_history(api):
    r = make(api)
    assert r['ok'] and r['rev'] == 1 and r['model']['key'] == 'x.client'
    lst = api.get(BASE)
    assert lst.headers['cache-control'] == 'no-store'
    body = lst.json()
    assert body['schema_version'] == 1 and body['rev'] == 1 and body['built_in'] is None
    (c,) = body['yours']
    assert c == {'key': 'x.client', 'name': 'client', 'label': 'Client', 'version': 1, 'base': 'core:record', 'base_label': 'Record',
                 'state': 'on', 'why': None, 'abstract': False, 'children': [], 'pending': None}
    assert {'key': 'core:record', 'label': 'Record', 'says': 'a record with an id'} in body['buildable']
    assert api.get(BASE + '?all=1').json()['built_in'] is not None
    page = api.get(BASE + '/x.client').json()
    names = [f['name'] for f in page['fields']]
    assert names == ['name', 'tier', 'phone', 'id'] and page['fields'][-1]['locked'] is True and page['fields'][-1]['from'] == 'Record'
    assert page['fields'][0] == {'name': 'name', 'label': 'Name', 'type': 'text', 'says': 'up to 80 characters, at least 1',
                                 'required': True, 'nullable': False, 'retired': False, 'aliases': [], 'from': 'Client', 'locked': False}
    assert page['chain'] == ['Record'] and page['rev'] == 1 and page['history_tail'][0]['says'] == 'made Client'
    shape = api.get(BASE + '/x.client/shape').json()
    assert shape['schema']['properties']['name']['maxLength'] == 80 and isinstance(shape['example'], dict)
    hist = api.get(BASE + '/x.client/history').json()['history']
    assert hist[0]['op'] == 'create' and hist[0]['class'] == 'same'


def test_the_read_models_fit_their_shapes(api):
    for n in ('client', 'vip_client', 'line', 'order'):
        make(api, n)
    page = api.get(BASE + '/x.vip_client').json()
    assert page['chain'] == ['Client', 'Record'] and page['fields'][0]['locked'] is False
    assert any(f['name'] == 'phone' and f['locked'] and f['from'] == 'Client' for f in page['fields'])
    order = api.get(BASE + '/x.order').json()
    assert [(l['name'], l['mode'], l['to_label']) for l in order['links']['out']] == [('lines', 'nest', 'Line'), ('client_id', 'refer', 'Client')]
    assert api.get(BASE + '/x.client').json()['links']['in'] == [{'from': 'x.order', 'from_label': 'Order', 'name': 'client_id', 'mode': 'refer'}]
    assert api.get(BASE).json()['yours'][0]['children'] == ['x.vip_client']
    g = api.get(BASE + '/graph').json()
    assert {n['key'] for n in g['nodes']} >= {'x.client', 'x.vip_client', 'x.order', 'core:record'}
    assert {(e['from'], e['to'], e['kind']) for e in g['edges']} >= {('x.vip_client', 'x.client', 'extends'), ('x.order', 'x.line', 'nests'),
                                                                     ('x.order', 'x.client', 'refers')}
    assert api.get(BASE + '/links').json() == {'links': [
        {'from': 'x.order/v1', 'field': 'lines', 'to': 'x.line/v1', 'status': 'ok'}, {'from': 'x.order/v1', 'field': 'client_id', 'to': 'x.client/v1', 'status': 'ok'}]}


def test_the_graph_text_names_every_edge(api):
    for n in ('client', 'vip_client', 'line', 'order'):
        make(api, n)
    g = api.get(BASE + '/graph').json()
    assert len(g['text']) == len(g['edges'])
    assert 'VIP client is a kind of Client' in g['text'] and 'Order holds Line (many) (needed)' in g['text'] and 'Order points at Client (needed)' in g['text']


def test_errors_unknown_model_name_taken_core_locked_stale_422_413(api):
    assert api.get(BASE + '/x.nothing').status_code == 404 and detail(api.get(BASE + '/x.nothing'))['code'] == 'UNKNOWN_MODEL'
    for tail in ('/shape', '/history'):
        assert api.get(BASE + '/x.nothing' + tail).status_code == 404
    make(api)
    r = api.post(BASE, json={'spec': dict(fix('client'), label='Other')})
    assert (r.status_code, detail(r)['code'], detail(r)['faults']) == (409, 'NAME_TAKEN', ['a model called Other is already there'])
    r = api.post(BASE + '/core:record', json={'spec': fix('client'), 'rev': 1})
    assert (r.status_code, detail(r)['code']) == (409, 'CORE_LOCKED')
    assert detail(r)['faults'] == ['Record is part of the app and cannot be changed']
    s = fix('client')
    s['about'] = 'x'
    r = api.post(BASE + '/x.client', json={'spec': s, 'rev': 0})
    assert (r.status_code, detail(r)['code']) == (409, 'STALE_REV')
    bad = fix('client')
    bad['fields'][0]['type'] = 'blob'
    r = api.post(BASE, json={'spec': bad})
    assert r.status_code == 422 and detail(r)['code'] == 'NOT_IN_SCHEMA' and 'is not one of text' in detail(r)['faults'][0]
    r = api.post(BASE + '/validate', content=b'{"sample":"' + b'x' * 140000 + b'"}', headers={'content-type': 'application/json'})
    assert r.status_code == 413
    other = api.post(BASE + '/x.client', json={'spec': fix('line'), 'rev': 1})
    assert other.status_code == 404


def test_429_when_the_writes_come_faster_than_one_a_second(api, monkeypatch):
    monkeypatch.setattr(store, 'MIN_GAP', 1.0)
    t = [50.0]
    monkeypatch.setattr(store, '_clock', lambda: t[0])
    store._LAST_WRITE[0] = 0.0
    make(api)
    s = fix('client')
    s['about'] = 'again'
    r = api.post(BASE + '/x.client', json={'spec': s, 'rev': 1})
    assert (r.status_code, detail(r)['code']) == (429, 'SLOW_DOWN')
    t[0] += 2
    assert api.post(BASE + '/x.client', json={'spec': s, 'rev': 1}).status_code == 200


def test_a_widening_is_a_pending_change_and_nothing_changes_until_the_stamp(api):
    make(api)
    wide = fix('client')
    wide['fields'][0]['max_len'] = 120
    r = api.post(BASE + '/x.client', json={'spec': wide, 'rev': 1}).json()
    assert r['pending'] is True and r['class'] == 'widens' and r['says'] == 'let name run to 120 characters'
    pid = r['pending_id']
    lst = api.get(BASE).json()
    assert lst['rev'] == 1 and lst['yours'][0]['pending']['id'] == pid
    assert api.get(BASE + '/x.client').json()['fields'][0]['says'] == 'up to 80 characters, at least 1'
    ok = api.post(BASE + '/pending/' + pid, json={'approve': True}).json()
    assert ok['ok'] and ok['rev'] == 2 and ok['model']['fields'][0]['says'] == 'up to 120 characters, at least 1'
    assert api.get(BASE).json()['yours'][0]['pending'] is None
    # No drops it
    wide['fields'][0]['max_len'] = 200
    pid = api.post(BASE + '/x.client', json={'spec': wide, 'rev': 2}).json()['pending_id']
    assert api.post(BASE + '/pending/' + pid, json={'approve': False}).json() == {'ok': True, 'dropped': True}
    assert api.get(BASE + '/x.client').json()['fields'][0]['says'] == 'up to 120 characters, at least 1'
    r = api.post(BASE + '/pending/p-00000000', json={'approve': True})
    assert (r.status_code, detail(r)['code']) == (404, 'UNKNOWN_PENDING')
    # a stale one
    wide['fields'][0]['max_len'] = 300
    pid = api.post(BASE + '/x.client', json={'spec': wide, 'rev': 2}).json()['pending_id']
    s = fix('client')
    s['fields'][0]['max_len'] = 120
    s['about'] = 'moved'
    assert api.post(BASE + '/x.client', json={'spec': s, 'rev': 2}).json()['ok']
    r = api.post(BASE + '/pending/' + pid, json={'approve': True})
    assert (r.status_code, detail(r)['code']) == (409, 'STALE_REV')


def test_enabled_undo_and_revert(api):
    make(api)
    make(api, 'vip_client')
    r = api.post(BASE + '/x.client/enabled', json={'enabled': False, 'rev': 2}).json()
    assert r['ok'] and r['model']['state'] == 'off'
    assert api.get(BASE + '/x.vip_client').json()['state'] == 'off'                       # by effect
    r = api.post(BASE + '/x.vip_client/enabled', json={'enabled': True, 'rev': 3})
    assert (r.status_code, detail(r)['code'], detail(r)['faults']) == (409, 'BASE_OFF', ['Client is off; turn it on first'])
    assert api.post(BASE + '/x.client/undo', json={'rev': 3}).json()['model']['state'] == 'on'
    r = api.post(BASE + '/x.client/revert', json={'to_rev': 1, 'rev': 4})
    assert r.status_code == 200 and r.json()['ok']
    r = api.post(BASE + '/x.client/revert', json={'to_rev': 99, 'rev': 5})
    assert (r.status_code, detail(r)['code']) == (404, 'UNKNOWN_MODEL')


def test_preview_writes_nothing(api, home):
    make(api)
    make(api, 'vip_client')
    before = (store._paths()[0].read_text(), store._paths()[1].read_text(), store.rev(), len(store.pending()))
    off = api.post(BASE + '/preview', json={'op': 'disable', 'key': 'x.client'}).json()
    assert off['ok'] and off['class'] == 'same' and off['affects']['turns_off'] == ['VIP client'] and off['needs_stamp'] is False
    wide = fix('client')
    wide['fields'][0]['max_len'] = 120
    p = api.post(BASE + '/preview', json={'op': 'edit', 'key': 'x.client', 'spec': wide}).json()
    assert p['class'] == 'widens' and p['needs_stamp'] is True and p['says'] == 'let name run to 120 characters'
    assert p['affects'] == {'turns_off': [], 'used_by': [], 'would_not_fit': [], 'unchecked': False}
    bad = fix('client')
    bad['fields'] = bad['fields'][:1]
    q = api.post(BASE + '/preview', json={'op': 'edit', 'key': 'x.client', 'spec': bad}).json()
    assert q['ok'] is False and q['faults'] == ['a field is retired, never removed']
    assert api.post(BASE + '/preview', json={'op': 'revert', 'key': 'x.client', 'to_rev': 1}).json()['ok']
    assert (store._paths()[0].read_text(), store._paths()[1].read_text(), store.rev(), len(store.pending())) == before


def test_validate_never_stores(api, home):
    make(api)
    ok = api.post(BASE + '/validate', json={'key': 'x.client', 'sample': {'id': 'c1', 'name': 'Asha'}}).json()
    assert ok == {'ok': True, 'faults': []}
    bad = api.post(BASE + '/validate', json={'key': 'x.client', 'sample': {'id': 'C 1', 'name': ''}}).json()
    assert bad['ok'] is False and any(f.startswith('$.id: does not match') for f in bad['faults']) and '$.name: shorter than 1' in bad['faults']
    spec = fix('line')
    before = (store._paths()[0].read_text(), store.rev())
    r = api.post(BASE + '/validate', json={'spec': spec, 'sample': {'id': 'l1', 'sku': 'A', 'qty': 0}}).json()
    assert r == {'ok': False, 'faults': ['$.qty: below 1']}
    assert (store._paths()[0].read_text(), store.rev()) == before and 'x.line' not in registry.current().state.__str__()
    loose = fix('vip_client')
    loose['fields'][0]['choices'] = ['gold', 'platinum']
    r = api.post(BASE + '/validate', json={'spec': loose, 'sample': {}}).json()
    assert r['ok'] is False and 'tier: adds platinum to the choices' in r['faults']
    r = api.post(BASE + '/validate', json={'key': 'x.nothing', 'sample': {}})
    assert r.status_code == 404


def test_a_deep_sample_is_refused(api):
    make(api)
    deep = cur = {}
    for _ in range(60):
        cur['a'] = {}
        cur = cur['a']
    r = api.post(BASE + '/validate', json={'key': 'x.client', 'sample': deep})
    assert r.status_code == 400 and detail(r)['code'] == 'TOO_DEEP'


def test_a_department_named_like_a_route_is_not_shadowed(tmp_path, monkeypatch):
    """A department ref `models` and one named `journeys` keep their routes; `_models` is no ref (it cannot begin with an underscore)."""
    monkeypatch.setenv('SUTRA_NATIVE_DEPT_HOME', str(tmp_path / 'departments'))
    monkeypatch.setenv('SUTRA_NATIVE_HOME', str(tmp_path / 'registry'))
    monkeypatch.setenv('SUTRA_UI_PROPOSALS', str(tmp_path / 'proposals'))
    monkeypatch.setenv('SUTRA_WEBSITE_OFFLINE', '1')
    monkeypatch.setattr(store, 'MIN_GAP', 0)
    import website_dept as W
    import placement_engine as E
    for m in (E, W):
        importlib.reload(m)
    if not E.active_roots(E.load_domains()):
        E.mint_domain(None, 'Sutra', ['Sutra'], 'T-local', origin='operator-request')
    registry.reset()
    import models_api
    import website_api
    importlib.reload(website_api)
    app = FastAPI()
    app.include_router(models_api.router)
    app.include_router(website_api.router)
    api = TestClient(app)
    for ref in ('models', 'journeys'):
        W.create(ref, ref.title(), 'A goal', kind='website')
    make(api)
    for ref in ('models', 'journeys'):
        got = api.get('/api/native/%s/map' % ref)
        assert got.status_code == 200 and set(got.json()) != set(), ref
        assert api.get('/api/native/%s/status' % ref).status_code == 200
    assert [m['key'] for m in api.get(BASE).json()['yours']] == ['x.client']
    assert W.slug('_models') == 'models'
    assert W.list_depts() and all(d['ref'] != '_models' for d in W.list_depts())
    paths = [getattr(r, 'path', '') for r in app.routes]
    assert paths.index(BASE) < paths.index('/api/native/{ref}/map')


def test_every_applied_change_leaves_a_row_in_roots_runs(api, home):
    import website_dept as W
    d = W.home() / 'org-root'
    d.mkdir(parents=True)
    (d / 'dept.json').write_text(json.dumps({'kind': 'root', 'ref': 'org-root', 'name': 'Org Root'}))
    make(api)
    s = fix('client')
    s['fields'].append(F('email', max_len=60))
    api.post(BASE + '/x.client', json={'spec': s, 'rev': 1})
    api.post(BASE + '/x.client/enabled', json={'enabled': False, 'rev': 2})
    api.post(BASE + '/x.client/undo', json={'rev': 3})
    rows = [r['what'] for r in W.runs('org-root')]
    assert len(rows) == 4 and rows[1] == 'the owner changed Client: added the field email'
    assert rows[2] == 'the owner changed Client: turned Client off' and rows[3].startswith('the owner changed Client: undid')
