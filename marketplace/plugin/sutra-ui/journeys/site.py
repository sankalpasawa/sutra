"""journeys/site.py -- the site's own journey data, read (PRD A3.6, contract case JC-9).

test_fixtures/journeys/site-journeys-2.4.json is a saved copy of the site's data file (system/journeys.json, version 2.4 of
2026-10-01). It is the one reference a journey is held to: every row the site lists is in the journey, each edge hangs under
the same step, and the words are the site's. The file is read here with the standard library only, and is copied, never
edited; when the owner publishes version 2.5 the new file replaces it in the same commit as the journey data that follows it.

    load(path=None)    the saved file, parsed
    rows(data)         {journey id: {ids, edge_at, step_says, step_code, was_edge_at}}: every row the site lists
    blocks(data)       {journey id: {tag, today, was}} in the template's shape
    same(mine, site)   whether a journey's words are the site's: the token {helper} counts as the word Sutra

The words are the site's own, with the tags taken out. Nothing here imports the runtime or the interface.
"""
import html
import json
import re
from pathlib import Path

#: the saved copy the cases read (a test fixture: the runtime never needs it)
SAVED = Path(__file__).resolve().parent.parent / 'test_fixtures' / 'journeys' / 'site-journeys-2.4.json'
#: the site's lane keys -> the template's lane ids
LANE_ID = {'coord': 'coordination', 'engine': 'engines', 'adapt': 'adaptation'}
#: the first words of a status or of an edge's text -> the template's site_status word
PREFIXES = (('wanted', 'wanted'), ('built', 'built'), ('today', 'today'), ('open', 'open'), ('directed', 'directed'),
            ('partly built', 'partly'), ('not built', 'not_built'), ('to build', 'to_build'))


def clean(s):
    """The site's words with the tags out, the entities read, and the white space one space."""
    s = re.sub(r'<[^>]+>', '', s or '')
    s = html.unescape(s)
    return re.sub(r'\s+', ' ', s).strip()


def same(mine, site):
    """Whether a journey's words are the site's: the token {helper} counts as the site's word Sutra."""
    return (mine or '').replace('{helper}', 'Sutra') == (site or '')


def status_of(words):
    """The template's site_status word for the site's own status words, or for the prefix of an edge's text ('Wanted: ...')."""
    w = (words or '').lower()
    for prefix, status in PREFIXES:
        if w.startswith(prefix):
            return status
    return 'none'


def step_row(s):
    """A site step in the journey template's step shape (the site's own words; the state is the author's to bind, never typed)."""
    return {'n': str(s['n']), 'lane': LANE_ID.get(s['lane'], s['lane']), 'short': clean(s['short']), 'text': clean(s['text']),
            'site_function': clean(s.get('function')), 'site_status': status_of(clean(s.get('status'))),
            'site_says': clean(s.get('status')) or 'none', 'site_code': clean(s.get('code')), 'act': 'say'}


def edge_row(e):
    """A site edge in the template's edge shape; `site.text` is the site's words, and `mark` stays the owner's (keep, change, drop)."""
    text = clean(e['code_does'])
    return {'id': e['id'], 'at': str(e['at']), 'short': clean(e['short']), 'trigger': clean(e['edge']),
            'site': {'status': status_of(text), 'text': text}, 'code_does': '', 'outcome': {'kind': 'none', 'voice': 'none', 'golden': None}}


def load(path=None):
    """The saved site file (the one beside the fixtures unless `path` names another), parsed."""
    return json.loads(Path(path or SAVED).read_text(encoding='utf-8'))


def rows(data):
    """For each journey the site lists, every row it lists: ids as 'step:1', 'edge:J1.5', 'build:B1', 'direction:D-a',
    'sub:J2.a', 'quote:1', 'was:step:0a', 'was:edge:J2.1' and 'today'; where each edge hangs (`edge_at`, and `was_edge_at`);
    and each step's status words and Code column."""
    out = {}
    for j in data['journeys']:
        jid = j['id'].upper()
        r = {'ids': [], 'edge_at': {}, 'step_says': {}, 'step_code': {}}
        for s in j['steps']:
            r['ids'].append('step:%s' % s['n'])
            r['step_says'][str(s['n'])] = clean(s.get('status')) or 'none'
            r['step_code'][str(s['n'])] = clean(s.get('code'))
        for e in j['edges']:
            r['ids'].append('edge:%s' % e['id'])
            r['edge_at'][e['id']] = str(e['at'])
        r['ids'] += ['build:B%d' % (i + 1) for i, _ in enumerate(j.get('build') or [])]
        if jid == 'J1':
            r['ids'] += ['direction:%s' % x['id'] for x in data['directed']]
        r['ids'] += ['sub:%s' % s[0] for s in j.get('sub') or []]
        r['ids'] += ['quote:%d' % (i + 1) for i, _ in enumerate(j.get('said') or [])]
        w = j.get('was')
        if w:
            r['ids'] += ['was:step:%s' % s['n'] for s in w['steps']] + ['was:edge:%s' % e['id'] for e in w['edges']]
            r['was_edge_at'] = {e['id']: str(e['at']) for e in w['edges']}
        if j.get('today'):
            r['ids'].append('today')
        out[jid] = r
    return out


def blocks(data):
    """For each journey the site gives one: its tag, its `today` ({text, sources}) and the earlier version it keeps (`was`:
    {title, lanes, steps, edges}), in the template's shape."""
    out = {}
    for j in data['journeys']:
        jid = j['id'].upper()
        b = {}
        if j.get('tag'):
            b['tag'] = clean(j['tag'])
        if j.get('today'):
            t = clean(j['today'])
            text, _, src = t.partition(' Source: ')
            b['today'] = {'text': text.strip(), 'sources': src.strip()}
        w = j.get('was')
        if w:
            used = []
            for x in w['steps']:
                lane = LANE_ID.get(x['lane'], x['lane'])
                if lane not in used:
                    used.append(lane)
            b['was'] = {'title': clean(w['title']), 'lanes': used, 'steps': [step_row(s) for s in w['steps']],
                        'edges': [edge_row(e) for e in w['edges']]}
        if b:
            out[jid] = b
    return out
