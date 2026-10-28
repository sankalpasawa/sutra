"""A4-OWN O6: where an owner's model is accepted (A4.5.7): the five hooks, fits_model and the report.

The core definitions the hooks stand on are registered here by the test (a closed `artifact.template`, a closed `kind`, an open
`journey`) until A4-PORT registers the real ones; the hook reads them by name from the registry, so the same tests hold after."""
import copy
import json
from pathlib import Path
from typing import Annotated, Any

import pytest

from layer_models import hooks, registry, store
from layer_models.base import Closed, Open
from layer_models.types import Enum, Items, Str

HERE = Path(__file__).resolve().parent
FIX = json.loads((HERE / 'test_fixtures' / 'models' / 'owner' / 'specs.json').read_text(encoding='utf-8'))


class Template(Closed):
    __abstract__ = False
    __def__ = 'artifact.template'
    __extensible__ = True
    id: Annotated[str, Str(40, 1, word=True)]
    name: Annotated[str, Str(40, 1)]


class Kind(Closed):
    __abstract__ = False
    __def__ = 'kind'
    __extensible__ = True
    name: Annotated[str, Str(40, 1)]
    mode: Annotated[Any, Enum('a', 'b')] = None


class Journey(Open):
    __abstract__ = False
    __def__ = 'journey'
    __extensible__ = True
    id: Annotated[str, Str(20, 1, word=True)]


class JourneyFile(Closed):
    __abstract__ = False
    __def__ = 'journey.file'
    journeys: Annotated[list[Journey], Items(20)]


def F(n, t='text', **k):
    return dict(name=n, label=n.replace('_', ' ').title(), type=t, **k)


def spec(name, base, fields, **k):
    return dict(name=name, version=1, label=name.replace('_', ' ').title(), base=base, fields=fields, **k)


@pytest.fixture
def world(tmp_path, monkeypatch):
    import layer_models
    layer_models.load()                  # the real definitions first, so the stand-ins below are not replaced by a later load
    monkeypatch.setenv('SUTRA_NATIVE_DEPT_HOME', str(tmp_path / 'departments'))
    monkeypatch.setattr(store, 'MIN_GAP', 0)
    for n, c in (('artifact.template', Template), ('kind', Kind), ('journey', Journey), ('journey.file', JourneyFile)):
        monkeypatch.setitem(registry.DEF_CLASS, n, c)
    for n in ('artifact.template', 'kind', 'journey', 'journey.file'):
        registry._ADAPTERS.pop(n, None)
    monkeypatch.setattr(registry, 'core_map', _core)
    registry.reset()
    hooks._NOTES.clear()
    yield
    registry.reset()
    for n in ('artifact.template', 'kind', 'journey', 'journey.file'):
        registry._ADAPTERS.pop(n, None)


def _core():
    from layer_models.owner_base import OwnerRecord
    return {'core:record': OwnerRecord, 'core:artifact.template': Template, 'core:kind': Kind, 'core:journey': Journey}


def visit_note(**k):
    return spec('visit_note', 'core:artifact.template', [F('summary', 'long_text', max_len=500, required=True)], **k)


def visit_record():
    return spec('visit_note', 'core:record', [F('summary', 'long_text', max_len=500, required=True)])


def make(*specs):
    for s in specs:
        store.save(s)


def test_a_template_that_names_a_model_validates_as_that_child(world):
    make(visit_note())
    ok = {'id': 't1', 'name': 'Visit', 'summary': 'went well', 'model': 'x.visit_note'}
    assert hooks.validate('artifact.template', ok) == []
    assert hooks.validate('artifact.template', dict(ok, summary='')) == []                 # long text may be empty
    bad = {k: v for k, v in ok.items() if k != 'summary'}
    assert hooks.validate('artifact.template', bad) == ['$.summary: is missing']
    # the base is checked first, on the value without the model key and the added fields
    assert hooks.validate('artifact.template', dict(ok, name='')) == ['$.name: shorter than 1']
    # a value that names no model is the definition's own business
    assert hooks.route('artifact.template', {'id': 't', 'name': 'N'}) is None
    assert hooks.validate('artifact.template', {'id': 't', 'name': 'N', 'summary': 'x'}) == ['$.summary: is not a field here']


def test_a_closed_base_kind_and_a_child_that_adds_a_field(world):
    make(spec('shop', 'core:kind', [F('hours', max_len=40, required=True)]))
    assert hooks.validate('kind', {'name': 'Shop', 'hours': '9 to 5', 'model': 'x.shop'}) == []
    assert hooks.validate('kind', {'name': 'Shop', 'model': 'x.shop'}) == ['$.hours: is missing']
    assert hooks.validate('kind', {'name': 'Shop', 'hours': 'x', 'extra': 1, 'model': 'x.shop'}) == ['$.extra: is not a field here']
    assert hooks.validate('kind', {'name': 'Shop', 'mode': 'zzz', 'hours': 'x', 'model': 'x.shop'}) == ['$.mode: is not one of a, b']


def test_a_journey_files_list(world):
    make(spec('tour', 'core:journey', [F('stop', max_len=20, required=True)]))
    good = {'journeys': [{'id': 'J1'}, {'id': 'J2', 'stop': 'x', 'model': 'x.tour'}]}
    assert hooks.validate('journey.file', good) == []
    bad = {'journeys': [{'id': 'J1', 'model': 'x.tour'}, {'id': 'J2', 'stop': 'ok', 'model': 'x.tour'}]}
    assert hooks.validate('journey.file', bad) == ['$.journeys[0].stop: is missing']
    assert hooks.validate('journey', {'id': 'J1', 'stop': 'x', 'model': 'x.tour'}) == []


def test_an_unknown_model_is_a_fault_and_a_model_that_is_off_is_not(world):
    ok = {'id': 't1', 'name': 'Visit', 'model': 'x.nothing'}
    assert hooks.validate('artifact.template', ok) == ['$.model: x.nothing is no model of yours']
    make(visit_note())
    store.set_enabled('x.visit_note', False)
    assert hooks.validate('artifact.template', {'id': 't1', 'name': 'Visit', 'model': 'x.visit_note'}) == []
    assert 'uses Visit Note, which is off' in hooks.report()
    # the wrong kind of model for the place
    make(spec('shop', 'core:kind', []))
    assert hooks.validate('artifact.template', {'id': 't1', 'name': 'V', 'model': 'x.shop'}) == ['$.model: Shop cannot be used here']


def test_an_exact_version_names_that_version(world):
    make(visit_note())
    v2 = dict(spec('visit_note', 'core:artifact.template', [F('summary', 'long_text', max_len=400, required=True),
                                                           F('mood', max_len=10, required=True)], parent='x:visit_note/v1'), version=2)
    store.save(v2)
    v = {'id': 't', 'name': 'V', 'summary': 's'}
    assert hooks.validate('artifact.template', dict(v, model='x.visit_note/v1')) == []
    assert hooks.validate('artifact.template', dict(v, model='x.visit_note')) == ['$.mood: is missing']


def files(**by):
    return {k: json.dumps(v) if not isinstance(v, str) else v for k, v in by.items()}


def test_a_filing_is_held_to_its_model_by_artifacts_check(world, monkeypatch):
    import artifacts
    make(visit_record())
    tpl = {'id': 'visit', 'name': 'Visit', 'kind': 'record', 'model': 'x.visit_note', 'checks': []}
    monkeypatch.setitem(artifacts.templates(), 'Visit', tpl)
    good = artifacts.check('Visit', files(**{'a.json': {'id': 'n1', 'summary': 's'}}))
    assert good == {'ok': True, 'notes': []}
    two = artifacts.check('Visit', files(**{'a.json': [{'id': 'n1', 'summary': 's'}, {'id': 'n2'}]}))
    assert two['ok'] is False and two['notes'] == ['a.json: $.summary: is missing']
    assert artifacts.check('Visit', files(**{'a.json': '{not json'}))['notes'] == ['a.json: is not JSON']
    assert artifacts.check('Visit', {'notes.md': 'free text'}) == {'ok': True, 'notes': []}       # only .json files are held to it


def test_a_model_that_is_off_passes_with_a_note(world, monkeypatch):
    import artifacts
    make(visit_record())
    store.set_enabled('x.visit_note', False)
    tpl = {'id': 'visit', 'name': 'Visit', 'kind': 'record', 'model': 'x.visit_note', 'checks': []}
    monkeypatch.setitem(artifacts.templates(), 'Visit', tpl)
    assert artifacts.check('Visit', files(**{'a.json': {'nonsense': 1}})) == {'ok': True, 'notes': ['Visit Note is off']}
    assert hooks.fits_model('x.nothing', {}) == {'ok': True, 'notes': ['x.nothing is no model of yours']}
    assert 'Visit uses Visit Note, which is off' in hooks.report()


def test_the_existing_check_of_a_template_without_a_model_is_unchanged(world):
    import artifacts
    names = [n for n, t in artifacts.templates().items() if t.get('checks') and not t.get('model')]
    assert names
    for n in names:
        assert artifacts.check(n, {}) is not None
    assert artifacts.check('No such template at all', {}) is None
