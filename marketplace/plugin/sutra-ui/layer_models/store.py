"""Where the owner's models are kept, and how they change (A4.5.3, A4.6.3).

    <records home>/_models/models.json     {schema_version, rev, models: {'client/v1': spec}}
                           history.jsonl   one line for each change, append only (rolls at 5 MB)
                           pending.json    changes that let in more, waiting for the owner's stamp

The owner is the actor on the Models screen, so a change that only tightens or leaves what fits as it was is applied at once and
told afterwards, with an undo. A change that lets in more waits for the owner's stamp (approvals only tighten, S-08): it is kept
as a pending change, not an ask (A4-10), and nothing changes until the stamp. Every applied change leaves a row on Root's runs.
The app is imported inside the functions that need it: this package imports nothing of the app at import time."""
import copy
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

import json_store

from . import bus, compile as _compile, owner_rules, registry, spec as SP
from .spec import LIMITS

STALE_REV = 'STALE_REV'
SLOW_DOWN = 'SLOW_DOWN'
MIN_GAP = 1.0                       # seconds between two writes from the screen
HISTORY_MAX = 5 * 1024 * 1024
_LOCK = threading.RLock()
_LAST_WRITE = [0.0]
_clock = time.monotonic


class ModelFault(Exception):
    """A change that cannot be made. `code` is one of A4.5.5, `faults` the sentences in the owner's words, `status` the HTTP
    answer a route gives (409, 404 or 429)."""

    def __init__(self, code, faults, status=409):
        super().__init__('%s: %s' % (code, '; '.join(faults)))
        self.code, self.faults, self.status = code, list(faults), status


class Pending(dict):
    """The answer to a change that waits for the owner's stamp: {ok, pending, class, pending_id, says}."""


def _now():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def _dir():
    import website_dept as W
    return W.home() / '_models'


def _paths():
    d = _dir()
    return d / 'models.json', d / 'history.jsonl', d / 'pending.json'


def source():
    """(path, stamp) of models.json: what a registry is built from. The stamp is None for no file."""
    try:
        p = _paths()[0]
    except Exception:  # noqa: BLE001 -- no records home (a test that has not bound one): no models
        return (None, None)
    try:
        st = p.stat()
        return (str(p), (st.st_mtime_ns, st.st_size))
    except OSError:
        return (str(p), None)


def _empty():
    return {'schema_version': 1, 'rev': 0, 'models': {}}


def _read_doc():
    """models.json as a dict; the specs are not checked here (load does that). A file that does not parse reads as empty and
    is left where it is (nothing is rewritten by a read)."""
    path = _paths()[0]
    doc = json_store.read_json(path, {})
    if not doc.get('models') and not isinstance(doc.get('models'), dict):
        return _empty(), path.exists()
    if not isinstance(doc.get('models'), dict):
        return _empty(), True
    doc.setdefault('rev', 0)
    return doc, False


def sha(spec):
    return _compile.sha(spec) if spec is not None else None


def load():
    """The document now, with the bad entries kept and marked: {rev, models: {key: spec}, bad: {key: [sentence]}}. Nothing is
    deleted or rewritten. The core bases are checked against the saved ones again (rebase)."""
    with _LOCK:
        doc, broken = _read_doc()
        good, bad = {}, {}
        for k, s in doc['models'].items():
            f = SP.check(SP.ModelSpec, s) if isinstance(s, dict) else ['$: is not an object']
            if f or (isinstance(s, dict) and SP.key_of(s) != k):
                bad[k] = f or ['$: the key does not match the model']
            else:
                good[k] = s
        return {'rev': doc.get('rev', 0), 'models': good, 'bad': bad, 'broken': broken}


def reload():
    """Build the registry from the file and swap it in."""
    with _LOCK:
        rebase()
        d = load()
        reg = _compile.compile_all(d['models'], registry.core_map(), reuse=registry._CURRENT)
        if d['bad']:                                           # kept, marked, left out of the compile
            state, why, faults = dict(reg.state), dict(reg.why), dict(reg.faults)
            for k, f in d['bad'].items():
                state['x.' + k], why['x.' + k] = 'needs_a_look', f[0]
                faults['x.' + k] = [('BAD_SPEC', f[0])]
            reg = registry.Registry(reg.core, reg.classes, reg.adapters, reg.specs, state, why, reg.families, faults)
        registry.swap(reg, source())
        return reg


def rev():
    return _read_doc()[0].get('rev', 0)


_BASE_SHA = {}


def base_sha(cls):
    """The sha of a core base's export (kept by class: a core class does not change while the app runs)."""
    h = _BASE_SHA.get(cls)
    if h is None:
        from .schema import export
        h = _BASE_SHA[cls] = _compile.sha(export(cls))
    return h


def _spec_for(spec, by, now, created=None):
    s = copy.deepcopy(spec)
    core = registry.core_map()
    if (s.get('base') or '') in core:
        try:
            s['base_sha'] = base_sha(core[s['base']])
        except Exception:  # noqa: BLE001 -- a base with no export keeps no sha
            pass
    s['schema_version'] = 1
    s.setdefault('enabled', True)
    if s.get('enabled') is None:
        s['enabled'] = True
    s['created'] = created or s.get('created') or now
    s['updated'] = now
    s['by'] = by
    return s


# ---- history ------------------------------------------------------------------------------------------------------------
def _append(line):
    p = _paths()[1]
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        if p.exists() and p.stat().st_size > HISTORY_MAX:
            os.replace(p, p.with_name('history.1.jsonl'))
    except OSError:
        pass
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(line, ensure_ascii=False) + '\n')


def history(key=None, limit=500):
    """The last `limit` lines (oldest first), of one model when `key` is given ('x.client' or 'client/v1' or 'x.client/v1')."""
    p = _paths()[1]
    rows = []
    for f in (p.with_name('history.1.jsonl'), p):
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                for ln in fh:
                    try:
                        rows.append(json.loads(ln))
                    except ValueError:
                        continue
        except OSError:
            continue
    if key:
        base = key[2:] if key.startswith('x.') else key
        rows = [r for r in rows if r.get('key') == 'x.' + base or (('/v' not in base) and r.get('key', '').startswith('x.' + base + '/v'))]
    return rows[-limit:]


def _root_row(what):
    """One row on the Root department's runs (as website_dept.set_host leaves one), so the spot checks and the messages see it."""
    try:
        import website_dept as W
        for d in W.list_depts():
            if d.get('kind') == 'root' and d.get('ref'):
                W.system_run(d['ref'], 'Root', what)
                return
    except Exception:  # noqa: BLE001 -- the row is a courtesy to the audit; a change is never undone for want of it
        return


# ---- the says --------------------------------------------------------------------------------------------------------------
def _bound_words(f, g):
    """What changed in one field, in the owner's words."""
    n = f['name']
    out = []
    if f.get('retired') != g.get('retired') and g.get('retired'):
        return ['retired the field %s' % n]
    if g.get('max_len') != f.get('max_len') and g.get('max_len'):
        out.append('let %s run to %d characters' % (n, g['max_len']) if (f.get('max_len') or 200) < g['max_len'] else 'cut %s to %d characters' % (n, g['max_len']))
    if g.get('min_len') != f.get('min_len'):
        out.append('changed the shortest %s to %d' % (n, g.get('min_len') or 0))
    for k, w in (('minimum', 'lowest'), ('maximum', 'highest')):
        if g.get(k) != f.get(k):
            out.append('changed the %s %s' % (w, n))
    if g.get('choices') != f.get('choices'):
        out.append('changed the choices of %s' % n)
    if g.get('pattern') != f.get('pattern'):
        out.append('changed the pattern of %s' % n)
    if bool(g.get('required')) != bool(f.get('required')):
        out.append('made %s %s' % (n, 'needed' if g.get('required') else 'optional'))
    if g.get('max_items') != f.get('max_items') or g.get('unique') != f.get('unique'):
        out.append('changed the list %s' % n)
    if g.get('label') != f.get('label') and not out:
        out.append('changed the label of %s' % n)
    return out


def says(old, new):
    """The change in the owner's words: 'added the field phone'. A first save is 'made Client'."""
    if old is None:
        return 'made %s' % new['label']
    out = []
    of, nf = {f['name']: f for f in old.get('fields') or []}, {f['name']: f for f in new.get('fields') or []}
    for n, g in nf.items():
        if n not in of:
            alias = next((x for x in of if x in (g.get('aliases') or [])), None)
            out.append('renamed the field %s to %s' % (alias, n) if alias else 'added the field %s' % n)
        else:
            out += _bound_words(of[n], g)
    ol, nl = {l['name']: l for l in old.get('links') or []}, {l['name']: l for l in new.get('links') or []}
    out += ['added the link %s' % n for n in nl if n not in ol]
    out += ['turned off the link %s' % n for n, l in nl.items() if n in ol and l.get('enabled') is False and ol[n].get('enabled') is not False]
    if old.get('label') != new.get('label'):
        out.append('changed its label to %s' % new['label'])
    if old.get('about') != new.get('about'):
        out.append('changed the line about it')
    return ', '.join(out) or 'saved it again'


# ---- the write path ------------------------------------------------------------------------------------------------------
def _gap():
    now = _clock()
    if MIN_GAP and now - _LAST_WRITE[0] < MIN_GAP and _LAST_WRITE[0]:
        raise ModelFault(SLOW_DOWN, ['one change a second; try again'], 429)
    _LAST_WRITE[0] = now


def _doc_to_write():
    """The document for a change. A file that does not parse is kept as it is: a change is refused until the owner has looked."""
    doc, broken = _read_doc()
    if broken:
        raise ModelFault('BAD_FILE', ['the models file cannot be read; it was left as it is'])
    return doc


def _guard_rev(doc, rev_):
    if rev_ is not None and doc.get('rev', 0) != rev_:
        raise ModelFault(STALE_REV, ['something changed since you looked; reload'])


def _write_doc(doc):
    json_store.write_json(_paths()[0], doc)


def _commit(doc, key_file, new_spec, op, says_, klass, by, before):
    """Write the document and the history line, swap the registry, bump the bus and leave a row on Root. Returns the new rev."""
    doc['rev'] = doc.get('rev', 0) + 1
    doc['models'][key_file] = new_spec
    doc['schema_version'] = 1
    _write_doc(doc)
    _append({'rev': doc['rev'], 'at': _now(), 'by': by, 'op': op, 'key': 'x.' + key_file, 'says': says_, 'class': klass,
             'before_sha': sha(before), 'after_sha': sha(new_spec), 'spec': new_spec})
    reload()
    bus.bump(['x.' + key_file.split('/')[0], 'x.' + key_file])
    _root_row('the owner changed %s: %s' % (new_spec['label'], says_))
    return doc['rev']


def _set_of(doc, key_file, new_spec):
    s = dict(doc['models'])
    s[key_file] = new_spec
    return s


def _validate_new(doc, key_file, new, old, creating):
    """The faults of putting `new` in place of `old`: the spec's rules over the whole set, and the compile. Raises ModelFault."""
    specs = _set_of(doc, key_file, new)
    core = registry.core_map()
    found = []
    if creating and new['version'] == 1:
        found += owner_rules.names(new, doc['models'], creating=True)
    if creating and len(doc['models']) >= LIMITS['models']:
        found.append(('TOO_MANY', 'a file holds at most %d models' % LIMITS['models']))
    if old is not None:
        found += owner_rules.compare_specs(old, new)
        found += owner_rules.new_link_faults(old, new, specs)
    found += owner_rules.base_off(specs, key_file)
    reg = _compile.compile_all(specs, core, reuse=registry._CURRENT)
    found += [(c, s) for c, s in reg.faults.get('x.' + key_file, [])]
    found = list(dict.fromkeys(found))                           # each sentence once
    if found:
        raise ModelFault(found[0][0], [s for _, s in found])
    return reg


def _pending_list():
    return json_store.read_json(_paths()[2], [])


def _put_pending(rows):
    json_store.write_json(_paths()[2], rows)


def pending():
    return _pending_list()


def _classify(doc, key_file, new, reg_new, old):
    """rules.compare of the class now saved and the class the change would make; a rename is read as the same field."""
    if old is None:
        return 'same'
    core = registry.core_map()
    old_cls = _compile.compile_all(doc['models'], core, reuse=registry._CURRENT).classes.get('x.' + key_file)
    new_cls = reg_new.classes.get('x.' + key_file)
    if old_cls is None or new_cls is None:
        return 'same'
    renames = {a: f['name'] for f in new.get('fields') or [] for a in f.get('aliases') or []}
    if renames:
        spec2 = copy.deepcopy(old)
        for f in spec2['fields']:
            f['name'] = renames.get(f['name'], f['name'])
        try:
            old_cls = _compile.compile_one(spec2, _compile._Scope(core, doc['models'], dict(reg_new.classes)))
        except Exception:  # noqa: BLE001 -- a rename the compare cannot read is not 'same'
            return 'mixed'
    return owner_rules.classify(old_cls, new_cls)


def _hold(op, key_file, new, doc, text, klass, now):
    rows = _pending_list()
    if len(rows) >= LIMITS['pending']:
        raise ModelFault('TOO_MANY', ['%d changes are already waiting for your stamp' % LIMITS['pending']])
    pid = 'p-' + uuid.uuid4().hex[:8]
    rows.append({'id': pid, 'op': op, 'key': 'x.' + key_file, 'spec': new, 'base_rev': doc.get('rev', 0), 'says': text,
                 'class': klass, 'at': now})
    _put_pending(rows)
    _root_row('the owner asked to %s for %s; it waits for the owner\'s stamp' % (text, new['label']))
    return Pending({'ok': True, 'pending': True, 'class': klass, 'pending_id': pid, 'says': text})


def _latest_file_key(doc, key):
    """'x.client' / 'client' / 'client/v2' / 'x.client/v2' -> the file key; the latest version for a bare name."""
    k = key[2:] if key.startswith('x.') else key
    if '/v' in k:
        return k if k in doc['models'] else None
    vs = [s['version'] for s in doc['models'].values() if s['name'] == k]
    return '%s/v%d' % (k, max(vs)) if vs else None


def _need(doc, key):
    locked = owner_rules.core_locked(key)
    if locked:
        raise ModelFault('CORE_LOCKED', [s for _, s in locked])
    fk = _latest_file_key(doc, key)
    if fk is None:
        raise ModelFault('UNKNOWN_MODEL', ['there is no model %s' % key], 404)
    return fk


def _check_set(doc, fk, new):
    """The compiled registry of the set with `new` in place, or ModelFault with the first code and every sentence."""
    reg = _compile.compile_all(_set_of(doc, fk, new), registry.core_map(), reuse=registry._CURRENT)
    found = list(reg.faults.get('x.' + fk, []))
    if found:
        raise ModelFault(found[0][0], [s for _, s in found])
    return reg


def _prepare_edit(doc, spec, by, create=False):
    key_file = SP.key_of(spec)
    old = doc['models'].get(key_file)
    if create and any(m.get('name') == spec['name'] for m in doc['models'].values()):
        raise ModelFault('NAME_TAKEN', ['a model called %s is already there' % spec.get('label', spec['name'])])
    new = _spec_for(spec, by, _now(), (old or {}).get('created'))
    reg = _validate_new(doc, key_file, new, old, creating=old is None)
    return {'fk': key_file, 'old': old, 'new': new, 'reg': reg, 'class': _classify(doc, key_file, new, reg, old),
            'says': says(old, new), 'op': 'create' if old is None else 'edit'}


def _prepare_enable(doc, key, enabled, by):
    fk = _need(doc, key)
    old = doc['models'][fk]
    new = _spec_for(dict(old, enabled=bool(enabled)), by, _now(), old.get('created'))
    reg = _validate_new(doc, fk, new, old, creating=False)
    return {'fk': fk, 'old': old, 'new': new, 'reg': reg, 'class': 'same', 'op': 'enable' if enabled else 'disable',
            'says': 'turned %s %s' % (old['label'], 'on' if enabled else 'off')}


def _prepare_undo(doc, key, by):
    fk = _need(doc, key)
    old = doc['models'][fk]
    rows = [r for r in history('x.' + fk) if r.get('op') not in ('rebase', 'base_changed') and r.get('spec')]
    target = rows[-2]['spec'] if len(rows) >= 2 else dict(old, enabled=False)
    new = _spec_for(target, by, _now(), old.get('created'))
    reg = _check_set(doc, fk, new)
    return {'fk': fk, 'old': old, 'new': new, 'reg': reg, 'class': 'same', 'op': 'revert',
            'says': 'undid the last change to %s' % old['label']}


def _prepare_revert(doc, key, to_rev, by):
    fk = _need(doc, key)
    row = next((r for r in history('x.' + fk, 100000) if r.get('rev') == to_rev and r.get('spec')), None)
    if row is None:
        raise ModelFault('UNKNOWN_MODEL', ['there is no revision %s of %s' % (to_rev, key)], 404)
    old = doc['models'][fk]
    new = _spec_for(row['spec'], by, _now(), old.get('created'))
    reg = _check_set(doc, fk, new)
    return {'fk': fk, 'old': old, 'new': new, 'reg': reg, 'class': _classify(doc, fk, new, reg, old), 'op': 'revert',
            'says': 'went back to revision %d of %s' % (to_rev, old['label'])}


def _finish(doc, p, by):
    """Apply a prepared change, or hold it for the stamp when it lets in more."""
    if p['class'] in ('widens', 'mixed'):
        return _hold(p['op'], p['fk'], p['new'], doc, p['says'], p['class'], _now())
    r = _commit(doc, p['fk'], p['new'], p['op'], p['says'], p['class'], by, p['old'])
    return {'ok': True, 'rev': r, 'class': p['class'], 'key': 'x.' + p['fk']}


def save(spec, rev=None, by='the owner', create=False):
    """Make a model or change one (a version of a name is the key 'name/vN'). A change that only tightens or leaves what fits is
    applied: {ok, rev, class, key}. A change that lets in more is kept for the stamp: a Pending. ModelFault otherwise. With `create`
    the name must be new (NAME_TAKEN otherwise); without it an existing key is an edit."""
    with _LOCK:
        _gap()
        doc = _doc_to_write()
        _guard_rev(doc, rev)
        return _finish(doc, _prepare_edit(doc, spec, by, create), by)


def set_enabled(key, enabled, rev=None, by='the owner'):
    """The model's own switch (R9). Turning on a child whose base is off is BASE_OFF; nothing is deleted either way."""
    with _LOCK:
        _gap()
        doc = _doc_to_write()
        _guard_rev(doc, rev)
        return _finish(doc, _prepare_enable(doc, key, enabled, by), by)


def undo(key, rev=None, by='the owner'):
    """The exact state before the last change of this model, which the owner had. Direct. The first change of a model is undone
    by turning it off (nothing is deleted)."""
    with _LOCK:
        _gap()
        doc = _doc_to_write()
        _guard_rev(doc, rev)
        p = _prepare_undo(doc, key, by)
        r = _commit(doc, p['fk'], p['new'], p['op'], p['says'], 'same', by, p['old'])
        return {'ok': True, 'rev': r, 'class': 'same', 'key': 'x.' + p['fk']}


def revert(key, to_rev, rev=None, by='the owner'):
    """An older revision of the model, by comparison: direct when it tightens or leaves things as they are, else for the stamp."""
    with _LOCK:
        _gap()
        doc = _doc_to_write()
        _guard_rev(doc, rev)
        return _finish(doc, _prepare_revert(doc, key, to_rev, by), by)


def plan(op, by='the owner'):
    """What a change would do, written nowhere: {ok, faults, code, class, says, needs_stamp, new, reg, old}. `op` is
    {op: 'edit'|'enable'|'disable'|'revert', key, spec?, to_rev?}."""
    doc = _read_doc()[0]
    kind = op.get('op')
    try:
        if kind == 'edit':
            p = _prepare_edit(doc, op['spec'], by)
        elif kind in ('enable', 'disable'):
            p = _prepare_enable(doc, op['key'], kind == 'enable', by)
        elif kind == 'revert':
            p = _prepare_revert(doc, op['key'], int(op['to_rev']), by)
        else:
            raise ModelFault('UNKNOWN_OP', ['say edit, enable, disable or revert'])
    except ModelFault as e:
        return {'ok': False, 'faults': e.faults, 'code': e.code, 'class': None, 'says': '', 'needs_stamp': False}
    return dict(p, ok=True, faults=[], code=None, needs_stamp=p['class'] in ('widens', 'mixed'))


def apply_pending(pid, approve, by='the owner'):
    """The owner's stamp (approve) or No on a change that waits. A stale one (the file moved on) is dropped and says so."""
    with _LOCK:
        rows = _pending_list()
        row = next((r for r in rows if r['id'] == pid), None)
        if row is None:
            raise ModelFault('UNKNOWN_PENDING', ['no change like that is waiting'], 404)
        _put_pending([r for r in rows if r['id'] != pid])
        if not approve:
            _root_row('the owner said no to: %s' % row['says'])
            return {'ok': True, 'dropped': True}
        doc = _read_doc()[0]
        if doc.get('rev', 0) != row['base_rev']:
            raise ModelFault(STALE_REV, ['something changed since you asked; the change was dropped, ask again'])
        _gap()
        fk = row['key'][2:]
        old = doc['models'].get(fk)
        new = row['spec']
        specs = _set_of(doc, fk, new)
        reg = _compile.compile_all(specs, registry.core_map(), reuse=registry._CURRENT)
        if reg.faults.get('x.' + fk):
            raise ModelFault(reg.faults['x.' + fk][0][0], [s for _, s in reg.faults['x.' + fk]])
        r = _commit(doc, fk, new, 'stamp', row['says'], row['class'], by, old)
        return {'ok': True, 'rev': r, 'class': row['class'], 'key': row['key']}


def rebase():
    """A5.6: a spec keeps the sha of its base's export. When a core base has changed and the fields still fit, the sha is brought
    up to date (a `rebase` line); when they no longer fit, a `base_changed` line says so and the model is marked needs a look by
    the compile. Nothing is deleted."""
    with _LOCK:
        doc, _ = _read_doc()
        if not doc['models']:
            return
        core = registry.core_map()
        changed = False
        reg = None
        valid = load()['models']
        for fk, s in sorted(doc['models'].items()):
            if fk not in valid:
                continue                                       # a spec that needs a look is not touched
            base = s.get('base') or ''
            if not base.startswith('core:') or base not in core:
                continue
            try:
                now_sha = base_sha(core[base])
            except Exception:  # noqa: BLE001 -- a base that cannot be exported has no sha to keep
                continue
            if not s.get('base_sha'):
                s['base_sha'] = now_sha
                changed = True
                continue
            if s['base_sha'] == now_sha:
                continue
            if reg is None:
                reg = _compile.compile_all(doc['models'], core)
            if reg.faults.get('x.' + fk):
                last = [r for r in history('x.' + fk) if r.get('op') in ('base_changed', 'rebase')]
                if not last or last[-1].get('op') != 'base_changed' or last[-1].get('after_sha') != now_sha:
                    _append({'rev': doc.get('rev', 0), 'at': _now(), 'by': 'the app', 'op': 'base_changed', 'key': 'x.' + fk,
                             'says': 'its base changed: %s' % reg.faults['x.' + fk][0][1], 'class': None,
                             'before_sha': s['base_sha'], 'after_sha': now_sha, 'spec': s})
            else:
                _append({'rev': doc.get('rev', 0), 'at': _now(), 'by': 'the app', 'op': 'rebase', 'key': 'x.' + fk,
                         'says': 'its base changed and it still fits', 'class': 'same', 'before_sha': s['base_sha'],
                         'after_sha': now_sha, 'spec': s})
                s['base_sha'] = now_sha
                changed = True
        if changed:
            _write_doc(doc)
