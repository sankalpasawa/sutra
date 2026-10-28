"""A pytest plugin that records what the suite validates (A4.3.7, source three): `-p a4_record --a4-record-dir DIR`.

It wraps layer_schema.validate and layer_schema.faults for the session and appends (definition name, canonical value) to
DIR/<definition>.jsonl, deduplicated, at most 200 values of at most 8 KB for a definition. `faults` knows no name: the definition
is found by the identity of the schema it was given. The wrappers are taken off when the session ends. It records and rules
nothing: the answer of each call is the real one."""
import json
from pathlib import Path

PER_DEFINITION = 200
MAX_BYTES = 8 * 1024

_state = {'dir': None, 'seen': {}, 'orig': None}


def pytest_addoption(parser):
    parser.addoption('--a4-record-dir', default=None, help='record what the suite validates into this directory (A4 equivalence proof)')


def _canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)


def _note(name, value):
    try:
        text = _canon(value)
    except (TypeError, ValueError):
        return
    if len(text.encode('utf-8')) > MAX_BYTES:
        return
    rows = _state['seen'].setdefault(name, {})
    if text not in rows and len(rows) < PER_DEFINITION:
        rows[text] = True


def pytest_configure(config):
    dest = config.getoption('--a4-record-dir')
    if not dest:
        return
    import layer_schema as S
    _state['dir'] = Path(dest)
    _state['orig'] = (S.validate, S.faults)
    validate, faults = _state['orig']
    by_id = {}

    def names():
        if len(by_id) != len(S.DEFS):
            by_id.clear()
            by_id.update({id(d): n for n, d in S.DEFS.items()})
        return by_id

    def rec_validate(name, value):
        if name in S.DEFS:
            _note(name, value)
        return validate(name, value)

    def rec_faults(schema, value, path='$'):
        name = names().get(id(schema))
        if name is not None and path == '$':
            _note(name, value)
        return faults(schema, value, path)
    S.validate, S.faults = rec_validate, rec_faults


def pytest_unconfigure(config):
    if _state['orig'] is None:
        return
    import layer_schema as S
    S.validate, S.faults = _state['orig']
    _state['orig'] = None
    dest = _state['dir']
    dest.mkdir(parents=True, exist_ok=True)
    for name, rows in _state['seen'].items():
        path = dest / (name + '.jsonl')
        old = []
        if path.exists():
            old = [l for l in path.read_text(encoding='utf-8').splitlines() if l]
        merged = list(dict.fromkeys(old + list(rows)))[:PER_DEFINITION]
        path.write_text('\n'.join(merged) + '\n', encoding='utf-8')
    _state['seen'] = {}
