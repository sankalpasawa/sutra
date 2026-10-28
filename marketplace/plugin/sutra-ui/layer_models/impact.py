"""What a change to a model would touch, read and written nowhere (A4.6.5 `preview`).

`preview(op)` calls the store's plan and the comparison, then looks at who uses the model: the artifact templates that name it and,
by a bounded scan, the newest version of each filed work under such a template. The scan reads at most 200 files and for at most
2 seconds and says `unchecked` when it was cut short. It never writes."""
import json
import time

from . import owner_rules, registry, store

FILES = 200
SECONDS = 2.0


def _names_model(template, key, reg):
    m = (template or {}).get('model')
    if not m:
        return False
    return reg.resolve(m) == key or m == key or m == key.rsplit('/v', 1)[0]


def templates_using(key, reg=None):
    """[name] of the artifact templates whose `model` is this model (exact key 'x.client/v1')."""
    import artifacts
    reg = reg or registry.current()
    return sorted(n for n, t in artifacts.templates().items() if _names_model(t, key, reg))


def filed_for(key, reg=None):
    """[(dept ref, art, version row)] for the newest version of each filed work whose template names the model."""
    import artifacts
    import website_dept as W
    reg = reg or registry.current()
    names = set(templates_using(key, reg))
    out = []
    if not names:
        return out
    for d in W.list_depts():
        ref = d.get('ref')
        for art in (W.artifacts_of(d) if ref else ()):
            if art in names:
                row = W.latest(ref, art)
                if row:
                    out.append((ref, art, row))
    return out


def scan_filed(key, files=FILES, seconds=SECONDS, adapter=None, reg=None):
    """{would_not_fit: [{dept, art, v, file, says}], unchecked: bool, used_by: [..]}: each .json file of the newest version of each
    filed work, checked with `adapter` (the model as the change would make it; the model as it is when none)."""
    import website_dept as W
    from .faults import sentences
    reg = reg or registry.current()
    ad = adapter if adapter is not None else (reg.families.get(key) or reg.adapters.get(key))
    t0, seen, bad, used, cut = time.monotonic(), 0, [], [], False
    for ref, art, row in filed_for(key, reg):
        used.append({'kind': 'filed', 'name': art, 'art': art, 'v': row['v'], 'dept': ref})
        if ad is None:
            continue
        for fname, text in sorted(W.read_files(ref, art, row['v']).items()):
            if not fname.endswith('.json'):
                continue
            if seen >= files or time.monotonic() - t0 > seconds:
                cut = True
                break
            seen += 1
            try:
                value = json.loads(text)
            except ValueError:
                bad.append({'dept': ref, 'art': art, 'v': row['v'], 'file': fname, 'says': 'is not JSON'})
                continue
            for item in (value if isinstance(value, list) else [value]):
                got = sentences(ad, item)
                if got:
                    bad.append({'dept': ref, 'art': art, 'v': row['v'], 'file': fname, 'says': got[0]})
                    break
        if cut:
            break
    return {'would_not_fit': bad, 'unchecked': cut, 'used_by': used}


def preview(op):
    """{ok, class, faults, affects: {turns_off, used_by, would_not_fit, unchecked}, needs_stamp, says}. Writes nothing."""
    p = store.plan(op)
    out = {'ok': p['ok'], 'class': p.get('class'), 'faults': list(p['faults']), 'code': p.get('code'),
           'affects': {'turns_off': [], 'used_by': [], 'would_not_fit': [], 'unchecked': False},
           'needs_stamp': p['needs_stamp'], 'says': p.get('says') or ''}
    if not p['ok']:
        return out
    reg_now, reg_new, fk = registry.current(), p['reg'], p['fk']
    key = 'x.' + fk
    specs_new = reg_new.specs
    # who turns off by effect: every model on now that would not be on after
    out['affects']['turns_off'] = sorted(
        owner_rules.label(specs_new, k[2:]) for k, st in reg_now.state.items()
        if st == 'on' and k != key and k[2:] in specs_new and reg_new.state.get('x.' + k[2:]) == 'off')
    tpl = templates_using(key, reg_new)
    out['affects']['used_by'] = [{'kind': 'artifact_template', 'name': n} for n in tpl]
    if tpl and p['class'] != 'same':
        ad = reg_new.families.get(key) or reg_new.adapters.get(key)
        scan = scan_filed(key, adapter=ad, reg=reg_new)
        out['affects']['used_by'] += scan['used_by']
        out['affects']['would_not_fit'] = scan['would_not_fit']
        out['affects']['unchecked'] = scan['unchecked']
    return out
