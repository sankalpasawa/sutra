"""The map of the owner's models (A4.6.4): who extends whom, who holds whom and who points at whom, as nodes, edges and the same
in sentences (a screen reader reads the sentences; the picture is only a view of them)."""
from . import owner_rules, registry


def _latest(reg):
    """The exact key of the latest version of each name, and the core keys they stand on."""
    best = {}
    for fk, s in reg.specs.items():
        if s['name'] not in best or s['version'] > reg.specs[best[s['name']]]['version']:
            best[s['name']] = fk
    return sorted(best.values())


def graph():
    """{nodes: [{key, label, core, state}], edges: [{from, to, kind, many, required}], text: [sentence]}."""
    reg = registry.current()
    specs = reg.specs
    nodes, edges, text, core_seen = [], [], [], {}

    def node_of(ref):
        if ref.startswith('core:'):
            core_seen[ref] = owner_rules.core_label(ref)
            return ref
        fk = owner_rules.ref_key(ref, specs)
        return 'x.' + fk.split('/')[0] if fk else ref

    for fk in _latest(reg):
        s = specs[fk]
        key = 'x.' + s['name']
        nodes.append({'key': key, 'label': s['label'], 'core': False, 'state': reg.state.get('x.' + fk, 'on')})
        base = s.get('base') or ''
        edges.append({'from': key, 'to': node_of(base), 'kind': 'extends', 'many': False, 'required': False})
        text.append('%s is a kind of %s' % (s['label'], owner_rules._label_of(base, specs)))
        for l in s.get('links') or []:
            kind = 'nests' if l['mode'] == 'nest' else 'refers'
            edges.append({'from': key, 'to': node_of(l['to']), 'kind': kind, 'many': bool(l.get('many')),
                          'required': bool(l.get('required'))})
            verb = 'holds' if kind == 'nests' else 'points at'
            text.append('%s %s %s%s%s' % (s['label'], verb, owner_rules._label_of(l['to'], specs), ' (many)' if l.get('many') else '',
                                          ' (needed)' if l.get('required') else ''))
    for ref, label in sorted(core_seen.items()):
        nodes.append({'key': ref, 'label': label, 'core': True, 'state': 'on'})
    return {'nodes': nodes, 'edges': edges, 'text': text}
