"""A4-UI: the read models test_models.js is built on are the real answers of the routes (A4.6.4), and the screen's banned words are the
interface's own (S.TEMPLATE_BANNED)."""
import copy
import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import layer_schema as S
from layer_models import registry, store

HERE = Path(__file__).resolve().parent
VIEWS = HERE / 'test_fixtures' / 'models' / 'views'
SPECS = json.loads((HERE / 'test_fixtures' / 'models' / 'owner' / 'specs.json').read_text(encoding='utf-8'))
BASE = '/api/native/_models'


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv('SUTRA_NATIVE_DEPT_HOME', str(tmp_path / 'departments'))
    monkeypatch.setattr(store, 'MIN_GAP', 0)
    registry.reset()
    import models_api
    import website_api
    app = FastAPI()
    app.include_router(models_api.router)
    app.include_router(website_api.router)
    yield TestClient(app)
    registry.reset()


def shape(v):
    """The keys of a value, down to its first list element; a value of a list is the shape of what it holds."""
    if isinstance(v, dict):
        return {k: shape(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [shape(v[0])] if v else []
    return type(v).__name__ if v is not None else 'null'


def fits(want, got, at='$'):
    """Every key of the fixture is a key of the answer, and the other way; a null may be anything; an empty list may hold anything."""
    if want == 'null' or got == 'null':
        return
    if isinstance(want, dict):
        assert isinstance(got, dict), at
        assert set(want) == set(got), (at, sorted(set(want) ^ set(got)))
        for k in want:
            fits(want[k], got[k], at + '.' + k)
    elif isinstance(want, list):
        assert isinstance(got, list), at
        if want and got:
            fits(want[0], got[0], at + '[]')
    else:
        assert want == got, (at, want, got)


def fixture(name):
    return json.loads((VIEWS / (name + '.json')).read_text(encoding='utf-8'))


def scenario(api):
    for n in ('client', 'line', 'order', 'vip_client', 'visit_note'):
        assert api.post(BASE, json={'spec': copy.deepcopy(SPECS[n + '/v1'])}).status_code == 200
    assert api.post(BASE + '/x.visit_note/enabled', json={'enabled': False, 'rev': api.get(BASE).json()['rev']}).status_code == 200
    wide = copy.deepcopy(SPECS['client/v1'])
    wide['fields'][0]['max_len'] = 120
    assert api.post(BASE + '/x.client', json={'spec': wide, 'rev': api.get(BASE).json()['rev']}).json()['pending']
    return wide


def test_the_view_fixtures_have_the_shape_of_the_routes(api):
    wide = scenario(api)
    tight = copy.deepcopy(SPECS['client/v1'])
    tight['fields'][0]['max_len'] = 60
    got = {
        'list': api.get(BASE).json(), 'list_all': api.get(BASE + '?all=1').json(), 'page': api.get(BASE + '/x.client').json(),
        'page_order': api.get(BASE + '/x.order').json(), 'graph': api.get(BASE + '/graph').json(),
        'history': api.get(BASE + '/x.client/history').json(), 'shape': api.get(BASE + '/x.client/shape').json(),
        'preview_tightens': api.post(BASE + '/preview', json={'op': 'edit', 'key': 'x.client', 'spec': tight}).json(),
        'preview_widens': api.post(BASE + '/preview', json={'op': 'edit', 'key': 'x.client', 'spec': wide}).json(),
        'preview_disable': api.post(BASE + '/preview', json={'op': 'disable', 'key': 'x.client'}).json(),
        'validate_bad': api.post(BASE + '/validate', json={'key': 'x.client', 'sample': {'id': 'C 1', 'name': '', 'tier': 'platinum'}}).json(),
    }
    for name, body in got.items():
        fits(shape(fixture(name)), shape(body), name)
    # the sentences the screen prints are the server's, as the fixture has them
    assert fixture('validate_bad')['faults'] == got['validate_bad']['faults']
    assert fixture('graph')['text'] == got['graph']['text']
    assert fixture('preview_disable')['affects']['turns_off'] == got['preview_disable']['affects']['turns_off']


def test_the_screen_is_held_to_the_interfaces_banned_words():
    js = (HERE / 'test_models.js').read_text(encoding='utf-8')
    m = re.search(r'const BANNED = /(.*)/i;', js)
    assert m and m.group(1) == S.TEMPLATE_BANNED, 'test_models.js BANNED must be S.TEMPLATE_BANNED'


def test_the_models_script_reads_no_route_but_the_models_routes():
    src = (HERE / 'static' / 'js' / '26-models.js').read_text(encoding='utf-8')
    assert re.findall(r'api(?:Get|Post)\(([^)]*)\)', src), 'it reads and writes'
    for call in re.findall(r'api(?:Get|Post)\(([^,)]*)', src):
        assert 'MDL_API' in call, call
    assert '/api/sessions' not in src and 'fetch(' not in src and 'localStorage' not in src
