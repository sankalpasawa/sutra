"""layers/audit/v1.py -- Audit, version 1: the implementation behind the interface's audit entries (PRD A1.18).

Its recipe is v1.json beside it: the Audit engine object. It starts on a checked version of the department's
deliverable ('$deliverable', whatever the kind), picks what to check, checks the record mechanically, reads each
done-when item (audit.items, in the S-30 shape), judges the pages against the brief, and files a reading.

Every code, prompt, draft and check name the recipe uses is provided here by reference (ref_to): the bodies stay in
engine_runtime's Audit region until they move, and a name the layer changes is copied into this module and changed here
(PRD A1.19). It holds its words (WORDS and LAYOUT, which layers/prompts.py compiles), so no part of it is read from
the .md bundle. view() is today's pane, by reference, with the readings of readings.jsonl added.

audit_mechanical is the first body to move (W2-CHECKS, M8.6): it checks the record as it always did, and the HTML of the
deliverable besides, without a browser: a link that goes to no page or anchor of the site, a form with no submit, an image
with no alt, a page with no h1 or with more than one, and a placeholder where a fact should be. Each defect is a finding
that names where it is (the page and the element) and what is wrong, and how serious it is; at most one for each element.
A defect of medium or high weight fails the measure, so a done-when item the measure covers does not hold; a low one is
filed and noted. It is the engine_runtime body's superset: the legacy body stays there as the fallback a broken layer
file leaves, and W3-PROOF deletes it.

Audit has a start of its own besides the version it reads (W3-BOARD, M8.7): a timer, every spot_every_s, held by its gate
audit.when until a minute in the period that a hash of the department's ref and the period gives. That run is the same steps with
the reading left out, and audit_file files a spot check: the state of the engines read, one audit.spot_check row, what it found
told to Identity. audit_pick, audit_file and audit_when are the layer's own for that; a start on a version goes to engine_runtime's
bodies as it always did.
"""
import hashlib
import json
import posixpath
import re
import time
from html import unescape
from html.parser import HTMLParser
from urllib.parse import unquote

from layers import R, W, J, S, FV, ref_to  # noqa: F401 -- lazy proxies: tests reload engine_runtime, so never a module object

LAYER = 'audit'
VERSION = 1
IMPLEMENTS = 1
RECIPE = 'v1.json'


# ---- the page checks of the mechanical step (M8.6): browser-free, one finding for each defect ---------------------------------
class _Page(HTMLParser):
    """One page, read once: its links with the words on them, its forms and whether each has a submit, its images and
    whether each has alt, its h1s, and every id and name an anchor can point at."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids, self.links, self.forms, self.images, self.h1s = set(), [], [], [], []
        self._words = []        # [(tag, record)]: the elements whose words are wanted, still open
        self._forms = []        # the forms still open, innermost last
        self._named = set()     # ids of forms a button outside them names (its form attribute)

    def _submit(self, a):
        if a.get('form'):
            self._named.add(a['form'])
        elif self._forms:
            self._forms[-1]['submit'] = True

    def handle_starttag(self, tag, attrs):
        a = {k: v if v is not None else '' for k, v in attrs}
        if a.get('id'):
            self.ids.add(a['id'])
        if tag == 'a' and a.get('name'):
            self.ids.add(a['name'])
        if tag == 'a' and 'href' in a:
            rec = {'href': a['href'], 'words': []}
            self.links.append(rec)
            self._words.append((tag, rec))
        elif tag == 'h1':
            rec = {'words': []}
            self.h1s.append(rec)
            self._words.append((tag, rec))
        elif tag == 'form':
            rec = {'label': a.get('aria-label') or a.get('name') or a.get('id') or '', 'id': a.get('id'), 'submit': False}
            self.forms.append(rec)
            self._forms.append(rec)
        elif tag == 'button':
            if a.get('type', 'submit').strip().lower() not in ('button', 'reset'):       # a button with no type submits
                self._submit(a)
        elif tag == 'input':
            if a.get('type', '').strip().lower() in ('submit', 'image'):
                self._submit(a)
        elif tag == 'img':
            self.images.append({'src': a.get('src', ''), 'alt': a.get('alt') if 'alt' in a else None})

    def handle_endtag(self, tag):
        if tag == 'form' and self._forms:
            self._forms.pop()
        for n in range(len(self._words) - 1, -1, -1):
            if self._words[n][0] == tag:
                del self._words[n]
                break

    def handle_data(self, data):
        for _, rec in self._words:
            rec['words'].append(data)

    def done(self):
        self.close()
        for f in self.forms:
            if f['id'] in self._named:
                f['submit'] = True
        return self


# The weight of a defect: medium fails the measure, low is filed and noted. A link to a page the site lacks, a form with no
# submit, an image with no alt and a page with no h1 weigh medium; a link to an anchor that is not there and a page with more
# than one h1 weigh low. A placeholder (a hole) weighs high, as it always did.
_ORDINAL = ('first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth')
_SCHEME = re.compile(r'^(?:[a-z][a-z0-9+.-]*:|//)', re.I)       # http:, mailto:, tel:, javascript:, data:, //host: not the site's own


def _clip(text, n=40):
    text = ' '.join(str(text or '').split())
    return text if len(text) <= n else text[:n - 1].rstrip() + '…'


def _filed(raw):
    """A page filed as {title, body_html} (the Pages form) as the dict it is; None for a page filed as it came."""
    text = str(raw)
    if text.lstrip().startswith('{'):
        try:
            data = json.loads(text)
        except ValueError:
            return None
        if isinstance(data, dict) and isinstance(data.get('body_html'), str):
            return data
    return None


def _html_of(raw):
    """A page's markup: the file as filed, or, for a page filed as {title, body_html} (the Pages form), its body."""
    data = _filed(raw)
    return data['body_html'] if data else str(raw)


def _own_title(raw):
    """The title a page carries: the Pages form's, or the <title> of a page filed whole; '' when it has none."""
    data = _filed(raw)
    if data:
        return _clip(data.get('title'), 60)
    found = re.search(r'<title[^>]*>(.*?)</title>', str(raw), re.I | re.S)
    return _clip(unescape(found.group(1)), 60) if found else ''


def _names(ref, files):
    """What the owner calls each HTML page of the version, by its file name: the title the department's site plan gives it
    (R._pages, as Identity's question to the owner names a page), 'Home' for the index, the title the page carries, else its file
    name read as words ('our-fees.html' as 'our fees'). A page is named, never given as a file."""
    try:
        planned = {str(p.get('slug')): _clip(p.get('title'), 60) for p in R._pages(ref) if isinstance(p, dict) and p.get('title')}
    except Exception:  # noqa: BLE001 -- a department with no readable site plan names its pages by what they carry
        planned = {}
    out = {}
    for name in files:
        if str(name).lower().endswith(('.html', '.htm')):
            slug = str(name).rsplit('.', 1)[0]
            out[name] = planned.get(slug) or ('Home' if slug == 'index' else '') or _own_title(files[name]) or re.sub(r'[\s/_-]+', ' ', slug).strip() or name
    return out


def _planned(files):
    """The pages a link may go to: the version's own HTML files, and the pages its plan names (_plan.json)."""
    names = {k for k in files if str(k).lower().endswith(('.html', '.htm'))}
    try:
        plan = json.loads(files.get('_plan.json') or '')
    except (TypeError, ValueError):
        plan = None
    if isinstance(plan, dict) and isinstance(plan.get('pages'), list):
        names |= {str(p['slug']).strip() + '.html' for p in plan['pages'] if isinstance(p, dict) and str(p.get('slug') or '').strip()}
    return names


def _defect(page, severity, element, claim):
    """One finding: where it is (`where`: the page and the element), what is wrong (`claim`, which names the element too, so
    it reads alone), and how serious. `page` is the page's own name, which the pane's notes and Identity's questions use."""
    return {'where': _clip('%s: %s' % (page, element), 200), 'page': _clip(page, 200), 'claim': _clip(claim, 600), 'severity': severity,
            'kind': 'defect'}


def _link_defects(name, page, planned, parsed):
    out = []
    for link in page.links:
        href = link['href'].strip()
        if not href or _SCHEME.match(href):
            continue
        path, _, frag = href.partition('#')
        path = unquote(path.split('?', 1)[0].strip())
        label = _clip(' '.join(link['words']))
        element = "the link '%s'" % label if label else 'a link'
        if not path:
            if frag not in ('', 'top') and frag not in page.ids:
                out.append(_defect(name, 'low', element, '%s goes to #%s, and nothing on the page has that anchor' % (element, _clip(frag))))
            continue
        target = posixpath.normpath(path.lstrip('/') if path.startswith('/') else posixpath.join(posixpath.dirname(name), path))
        target = 'index.html' if target in ('.', '') else target
        if not target.lower().endswith(('.html', '.htm')):
            continue                                             # a file that is not a page (a style, a picture) is not this check's
        if target not in planned:
            out.append(_defect(name, 'medium', element, '%s goes to %s, which is not a page of the site' % (element, _clip(target))))
        elif frag not in ('', 'top') and target in parsed and frag not in parsed[target].ids:
            out.append(_defect(name, 'low', element, '%s goes to %s#%s, and that page has no such anchor' % (element, _clip(target), _clip(frag))))
    return out


def _form_defects(name, page):
    out = []
    for n, f in enumerate(page.forms):
        if f['submit']:
            continue
        which = ("the form '%s'" % _clip(f['label'])) if f['label'] else (
            'the form' if len(page.forms) == 1 else 'the %s form' % (_ORDINAL[n] if n < len(_ORDINAL) else 'later'))
        out.append(_defect(name, 'medium', which, '%s has no submit button, so a visitor cannot send it' % which))
    return out


def _image_defects(name, page):
    out = []
    for img in page.images:
        if img['alt'] is None:
            which = ("the image '%s'" % _clip(posixpath.basename(img['src']))) if img['src'] else 'an image'
            out.append(_defect(name, 'medium', which, '%s has no alt text for a reader who cannot see it' % which))
    return out


def _heading_defects(name, page):
    heads = [_clip(' '.join(h['words'])) for h in page.h1s]
    if not heads:
        return [_defect(name, 'medium', 'the main heading (h1)', 'the page has no h1 heading')]
    if len(heads) > 1:
        return [_defect(name, 'low', 'the main heading (h1)',
                        'the page has more than one h1 heading, and should have one: %s' % ', '.join("'%s'" % h for h in heads))]
    return []


def page_defects(files):
    """The defects of the HTML pages of one version that no browser is needed to find, as findings {where, page, claim,
    severity, kind}: by page (sorted), then by element in the page's order, each defect once. A deliverable with no HTML page
    has none. A page that cannot be parsed is skipped, since Check says that of a page."""
    files = {k: v for k, v in (files or {}).items() if isinstance(k, str)}
    parsed = {}
    for name in sorted(k for k in files if k.lower().endswith(('.html', '.htm'))):
        try:
            parsed[name] = _Page()
            parsed[name].feed(_html_of(files[name]))
            parsed[name].done()
        except Exception:  # noqa: BLE001 -- a page that does not parse is Check's to refuse, not a second fault here
            parsed.pop(name, None)
    planned, out, seen = _planned(files), [], set()
    for name, page in parsed.items():
        for d in _link_defects(name, page, planned, parsed) + _form_defects(name, page) + _image_defects(name, page) + _heading_defects(name, page):
            if (d['where'], d['claim']) not in seen:
                seen.add((d['where'], d['claim']))
                out.append(d)
    return out


def _hole(hole):
    """A placeholder where a fact should be, as the legacy body finds it (R.placeholders), with `where` added: the page and the
    words that say it. `page` stays the page's name, which Identity's question to the owner is put by."""
    phrase = R.PLACEHOLDER.search(str(hole.get('claim') or ''))
    return dict(hole, where=_clip("%s: the text '%s'" % (hole.get('page'), phrase.group(0) if phrase else 'to be confirmed'), 200))


def _note(defect, names=None):
    """A defect as the mechanical step's notes say it: the page by the name the owner knows it by (`names`, from _names; its file
    name when it has none), then what is wrong (the claim names the element). The finding itself keeps the page's file name in
    `page` and `where`, which is what Identity maps to a title and what a link names."""
    return '%s: %s' % ((names or {}).get(defect['page'], defect['page']), defect['claim'])


def _has_pages(files):
    """Whether the version has an HTML page for the page checks to read."""
    return any(str(k).lower().endswith(('.html', '.htm')) for k in files)


def audit_mechanical(ctx, step, item):
    """Audit's code check of the record, and of the pages (M8.6). The record: every version has its run and its check, and the
    deliverable traces back to the owner's words. The pages: placeholders where a fact should be (holes, which Identity puts to
    the owner as a question for the facts), and the page defects of page_defects (defects, each a finding that names where and
    what). `ok` is false when the record has a fault, a page has a hole, or a defect weighs medium or high."""
    ref = ctx['ref']
    if not ctx['bag']['audit.pick']['sample']:
        return {'ok': True, 'notes': ['not sampled']}
    notes = []
    for a in W.artifacts_of(W.dept(ref))[1:]:
        for v in W.versions(ref, a):
            if not v.get('run') or 'check' not in v:
                notes.append('%s has a version with no run or no check' % a)
    art = R.audit_art(ctx)
    if not any(c.get('kind') == 'ask' for c in (W.trace(ref, art, ctx['inp']['v']) if art else [])):
        notes.append("the %s does not trace back to the owner's words" % (art or 'deliverable').lower())
    files = R.audit_files(ctx)
    # a page that says "to be confirmed" published what nobody knew (found live 2026-09-28: twelve such places on four
    # pages); Audit names each hole, Identity asks the owner for the facts instead of a stamp
    holes = [_hole(h) for h in R.placeholders(files)]
    defects = page_defects(files)
    failing = [d for d in defects if d['severity'] != 'low']
    said = notes + (['the site says it does not know %d thing%s' % (len(holes), '' if len(holes) == 1 else 's')] if holes else [])
    names = _names(ref, files)
    said += [_note(d, names) for d in failing[:4]] + (['more is wrong on the pages'] if len(failing) > 4 else [])
    noted = ['noted, ' + _note(d, names) for d in defects if d['severity'] == 'low'][:2]
    clean = "every version has its run and its check; the trace reaches the owner's words"
    if _has_pages(files):
        clean += "; the pages' links, forms, images and headings are in order"
    return {'ok': not said, 'notes': said + noted or [clean], 'faults': notes, 'holes': holes, 'defects': defects}


def has_a_verdict(ctx, step, item, out):
    """Audit's covering of the mechanical step: it gives a verdict (ok) with its notes, and each defect it names says where it
    is, what is wrong, and how serious (A1.12). A defect that does not fails the step, and the version is not read."""
    got = R.c_has_a_verdict(ctx, step, item, out)
    if not got['ok']:
        return got
    bad = ['defect %d names no %s' % (n, key) for n, d in enumerate(out.get('defects') or [], 1) if isinstance(d, dict)
           for key in ('where', 'claim') if not str(d.get(key) or '').strip()]
    bad += ['defect %d has no weight of high, medium or low' % n for n, d in enumerate(out.get('defects') or [], 1)
            if not isinstance(d, dict) or d.get('severity') not in S.SEVERITIES]
    return {'ok': not bad, 'notes': bad or got['notes']}


# ---- spot checks (PRD M8.7, W3-BOARD) ----------------------------------------------------------------------------------------
# Sporadic and unannounced (ruled 2026-09-27): Audit drops in on a department once in every spot_every_s, at a minute that is
# not fixed, and reads the state of its engines, nothing more. It is a start of its own (a timer, besides the version it reads),
# held by a gate of Audit's until its minute in the period. Its run is the steps of a reading with the reading left out: the
# steps that read a version are not needed, and the last one files the check. It reads runs and versions; it writes its own row
# of spot_checks.jsonl and tells Identity what it found, and nothing else (spot_check_reads_only).
SPOT_SEVERITY = 'medium'         # what a spot check's finding weighs: the record is wrong, and no reader has been misled by it
SPOT_SAYS = {True: 'looked in on the engines: every version has its run and its check, each run traces back, nothing is stuck',
             False: 'looked in on the engines and found something to put right'}
#: Audit's own rows in the journals the check reads, by the field that says whose a row is: they are not "outside Audit's rows"
_OWN_ROWS = {'runs.json': 'engine', 'steps.jsonl': 'engine', 'board.jsonl': 'src'}


def spot_every_s(e):
    """The period of Audit's timer start in a definition of the engine, in seconds (the setting's default when it names none)."""
    for t in ((e or {}).get('start') or {}).get('on') or []:
        if t.get('kind') == 'timer' and t.get('every_s'):
            return int(t['every_s'])
    return int(S.SETTINGS['audit']['spot_every_s']['default'])


def spot_jitter_s(ref, period, every_s):
    """Where in its period a department's spot check falls, in seconds: a whole minute, from a hash of the department's ref and
    the period's number, so it is not the same minute twice and not the same in two departments, and a replay says it again."""
    minutes = max(1, int(every_s) // 60)
    return 60 * (int(hashlib.sha256(('%s|%d' % (ref, int(period))).encode('utf-8')).hexdigest(), 16) % minutes)


def audit_when(ctx, step, item):
    """Audit's gate on its own starts (M8.7): a start on a version of the deliverable is let through; a timer start is let through
    at its minute in the period, and only for a department that was there when the period began (one made today is first looked
    in on in the next period), that is not Root, and that is not in the middle of a cycle (a spot check in the middle of its work
    would not be unannounced, it would be a second reading). Reads the record and the clock, and says no more than 'not yet'."""
    inp = ctx.get('inp') or {}
    if inp.get('timer') is None:
        return 'admit', None
    ref = ctx['ref']
    d = ctx.get('dept') or W.dept(ref) or {}
    if d.get('kind') == 'root':
        return 'wait', 'Audit does not look in on the organisation'
    if J.active(ref):
        return 'wait', 'the department is in the middle of its work'
    every = spot_every_s(ctx.get('def'))
    began = int(inp['timer']) * every
    if W._ts(d.get('created') or '') > began:
        return 'wait', 'the department was not there when this period began'
    if time.time() < began + spot_jitter_s(ref, inp['timer'], every):
        return 'wait', 'it is not yet time'
    return 'admit', None


def spot_state(ref):
    """The department's files as they stand, apart from Audit's own rows (its spot checks, and its rows in the runs, the steps and
    the board): one hash. A spot check takes it before and after it reads, and it is the same."""
    base = W.ddir(ref)
    h = hashlib.sha256()
    for p in sorted(base.rglob('*')):
        rel = p.relative_to(base).as_posix()
        if not p.is_file() or rel == 'spot_checks.jsonl' or rel.startswith('steps/Audit@') or p.name.startswith('.') or p.suffix == '.lock':
            continue
        try:
            data = p.read_bytes()
        except OSError:
            continue
        key = _OWN_ROWS.get(rel)
        if key:
            text = data.decode('utf-8', 'replace')
            try:
                rows = json.loads(text or '[]') if rel == 'runs.json' else [json.loads(ln) for ln in text.splitlines() if ln.strip()]
            except ValueError:
                rows = text
            if isinstance(rows, list):
                data = json.dumps([r for r in rows if not (isinstance(r, dict) and r.get(key) == 'Audit')], sort_keys=True).encode('utf-8')
        h.update(rel.encode('utf-8') + b'\0' + hashlib.sha1(data).digest())
    return h.hexdigest()[:24]


def spot_checks(ref, d, now=None, skip=None):
    """What a spot check reads of the engines' state, and nothing else: every version has a run and a check, each artifact's
    latest version traces back to the owner's words, and no run has been going past its window (its own run, `skip`, is the one
    that is looking). [{check, ok, why}], one for each, and a finding for each that does not hold, which names where it is. Reads
    runs and versions only."""
    now = time.time() if now is None else now
    arts = list(W.artifacts_of(d))[1:]
    no_run = sorted({a for a in arts for v in W.versions(ref, a) if not v.get('run') or 'check' not in v})
    untraced = sorted({a for a in arts if W.latest(ref, a) and
                       not any(c.get('kind') == 'ask' for c in W.trace(ref, a, W.latest(ref, a)['v']))})
    stuck = sorted({r['engine'] for r in W.runs(ref) if r.get('status') == 'running' and r.get('id') != skip and
                    now - W._ts(r.get('started') or '') > 60 * int((d.get('windows') or {}).get(r['engine']) or 30)})
    rows = [('every version has its run and its check', no_run, '%s has a version with no run or no check'),
            ("each run traces back to the owner's words", untraced, "%s does not trace back to the owner's words"),
            ('nothing is stuck past its window', stuck, '%s has been running past its window')]
    checks, found = [], []
    for name, bad, claim in rows:
        what = claim % ' and '.join(bad) if bad else None
        checks.append({'check': name, 'ok': not bad, 'why': (what or 'it holds')[:300]})
        if bad:
            found.append({'id': 'F%d' % (len(found) + 1), 'severity': SPOT_SEVERITY, 'claim': what[:600], 'where': ', '.join(bad)[:200],
                          'item': None, 'went_to': 'Identity', 'ask': None, 'at': W.now()})
    return checks, found


def audit_pick(ctx, step, item):
    """The first step of a reading, and of a spot check, which has no version to pick from: it is not a sample, and says so."""
    if (ctx.get('inp') or {}).get('timer') is not None:
        return {'sample': False, 'pages': [], 'spot': True}
    return R.audit_pick(ctx, step, item)


def spot_file(ctx):
    """The last step of a spot check: the state is read twice, with the department's lock held so that nothing else writes in
    between; a check that left it changed files nothing and says so (its covering fails it); else its row is one line of
    spot_checks.jsonl (once for a slot, so a replay writes it once) and its findings go to Identity, as Audit's findings do."""
    ref, d, slot = ctx['ref'], ctx.get('dept') or W.dept(ctx['ref']) or {}, ctx.get('slot') or ''
    with W._lock(ref):
        before = spot_state(ref)
        checks, found = spot_checks(ref, d, skip=ctx.get('run'))
        after = spot_state(ref)
    out = {'spot': True, 'before': before, 'after': after, 'checks': checks, 'findings': found, 'filed': len(found), 'read': None}
    if before != after:
        return dict(out, said="a spot check wrote outside Audit's rows, and filed nothing")
    n = int(ctx['inp']['timer'])
    every = spot_every_s(ctx.get('def'))
    row = {'schema_version': 1, 'id': 'sc-' + hashlib.sha1(slot.encode('utf-8')).hexdigest()[:8], 'at': W.now(),
           'minute': ((n * every + spot_jitter_s(ref, n, every)) % 86400) // 60, 'checks': checks, 'findings': found}
    if not any(r.get('id') == row['id'] for r in W.rows(ref, 'spot_checks.jsonl')):
        W.append_row(ref, 'spot_checks.jsonl', row)
        if found:
            R.post(ref, 'Audit', 'Identity', 'inform',
                   {'word': 'finding', 'claim': found[0]['claim'], 'severity': SPOT_SEVERITY, 'where': found[0]['where'], 'findings': found,
                    'spot': True})
    return dict(out, said=SPOT_SAYS[not found] + ('' if not found else ': ' + found[0]['claim']))


def audit_file(ctx, step, item):
    """Audit's filing: a reading's, as engine_runtime's body does it, or a spot check's."""
    if (ctx['bag'].get('audit.pick') or {}).get('spot'):
        return spot_file(ctx)
    return R.audit_file(ctx, step, item)


def spot_check_reads_only(ctx, step, item, out):
    """Audit's covering of its filing (M8.7): a spot check left the department's files as it found them, apart from Audit's own
    rows, said what it did, and files nothing otherwise; any other filing (a reading) says what it did, as every step does."""
    if not isinstance(out, dict) or not out.get('spot'):
        return R.c_said_what_it_did(ctx, step, item, out)
    if out.get('before') != out.get('after'):
        return {'ok': False, 'notes': ["a spot check wrote outside Audit's rows"]}
    if not str(out.get('said') or '').strip():
        return {'ok': False, 'notes': ['it did not say what it did']}
    return {'ok': True, 'notes': ["it read the engines' state and wrote only its own row"]}


CODE = {
    'audit_pick': audit_pick,
    'audit_mechanical': audit_mechanical,
    'audit_file': audit_file,
    'audit_when': audit_when,
}
PROMPT = {
    'audit_judge': ref_to('p_audit_judge'),
    'audit_items': ref_to('p_audit_items'),
}
DRAFT = {
    'audit_judge_draft': ref_to('d_audit_judge'),
    'audit_items_draft': ref_to('d_audit_items'),
}
CHECK = {
    'picked_a_sample': ref_to('c_picked_a_sample'),
    'has_a_verdict': has_a_verdict,
    'findings_name_where_and_what': ref_to('c_findings_name_where_and_what'),
    'said_what_it_did': ref_to('c_said_what_it_did'),
    'reading_is_s30': ref_to('c_reading_is_s30'),
    'gate_answer_is_known': ref_to('c_gate_answer_is_known'),        # shared (S.SHARED_CHECKS): the covering of its gate
    'spot_check_reads_only': spot_check_reads_only,
}
# Audit's words, by the split rule of A1.16 from function-prompts/audit/*.md (python -m layers.prompts --extract audit);
# judge.items is the part this layer added (A1-ITEMS), written in the bundle as the others are. The bundle is the
# fallback every department's own whole-file copy (M2.2) reads, and W3-PROOF deletes it.
WORDS = {
    'goal': {
        'does': {
            'text': 'drops in on what went live and checks claims against the record',
        },
        'skills': {
            'items': [
                'pick what to check',
                'check the record mechanically',
                'judge a page against the brief',
            ],
        },
    },
    'judge': {
        'judge': {
            'task': (
                'Check what the department made against what it was asked. Read the brief and what the '
                "department's own engines filed, then the pages. Find any statement of fact on a page that neither "
                'the brief nor a filed artifact gives: a phone number, an address, a date, a count, a name, a '
                'claim of history. A fact a filed artifact gives, with its source, is backed: do not report it.'
            ),
            'guidance': 'high: a reader could be harmed or misled by it. At most eight findings.',
        },
        'items': {
            'task': (
                'Read the work against what was asked, one done-when item at a time. For each item below give a '
                'verdict: met only when the work itself shows it; not met when the work leaves it out or shows it '
                'does not hold; to confirm when it rests on a fact only the owner can give, or the work cannot '
                'show it either way. Say in one line what is or is not true (the claim) and in one line what in '
                'the work shows it (the evidence). What code measured is given below: weigh it, and never call an '
                'item met that a measure shows failing.'
            ),
            'guidance': (
                'One row for every item, each under its own id, and no other row. A finding is something to put '
                'right that you saw while reading: say where it is and what is wrong, and name the item it belongs '
                'to, or null. high: a reader could be harmed or misled by it. Never guess a fact that neither the '
                'brief nor a filed artifact gives: a phone number, an address, a date, a count, a name. A fact a '
                'filed artifact gives, with its source, is backed: do not report it. At most eight findings.'
            ),
        },
    },
}
LAYOUT = {
    'goal': {
        'does': '{text}',
        'skills': '{items}',
    },
    'judge': {
        'judge': (
            '{task} {returns} {guidance}\n'
            '\n'
            'THE BRIEF:\n'
            '{{brief}}{{filed}}\n'
            '\n'
            'THE PAGES:\n'
            '{{pages}}'
        ),
        'items': (
            '{task}\n'
            '{returns}\n'
            '{guidance}\n'
            '\n'
            'THE BRIEF:\n'
            '{{brief}}{{filed}}\n'
            '\n'
            'THE DELIVERABLE:\n'
            '{{deliverable}}\n'
            '\n'
            'THE DONE-WHEN ITEMS:\n'
            '{{items}}\n'
            '\n'
            'WHAT CODE MEASURED:\n'
            '{{measured}}'
        ),
    },
}

# ---- the function template's words (A3.4.5, A3-FUNCTIONS F1) ---------------------------------------------------------
# Parts of the goal group that S.ADDED_PARTS lists (they have no .md part), and the layout of the role block the card
# carries (A3.4.3). What the function is not, what it never does and who it hands on to are S.FUNCTION_TEMPLATE's, not
# words: no version drops one.
WORDS['goal']['done'] = {'text': (
    'every version of the deliverable was read item by item, and every finding went to Identity, '
    'saying where it is and what it claims'
)}
WORDS['goal']['role_is'] = {'text': (
    "the department's independent second pair of eyes; it judges what was actually made against the "
    'goal, the done-when, the rules and the evidence'
)}
WORDS['goal']['role_may'] = {'items': [
    'read the result itself, not only the report of the engine that made it',
    'run the mechanical checks first',
    'check each claim that matters against the evidence',
    'file one finding for each separate issue, saying where it is and what it claims',
    'mark an item to be confirmed when the evidence is missing, and say so instead of guessing',
    'say whether a done check can be audited',
    'drop in unannounced on the state of the engines',
]}
WORDS['goal']['role_procedure'] = {'items': [
    'Read the result itself, not only what its maker said.',
    'Run the mechanical checks first.',
    'Check each claim that matters against the evidence you have.',
    'Compare the result with the done check and the goal and rules that apply.',
    'File one finding for each separate issue.',
    (
        'Send what is a matter of the rules, and what can be put right, to Identity, which decides '
        'what goes back to Adaptation.'
    ),
    'When the evidence is missing, mark the item to be confirmed; do not guess.',
]}
WORDS['goal']['role_patterns'] = {'items': [
    'Rewriting the work while auditing it.',
    'Taking a matter of taste for a failure.',
    'Inventing evidence.',
    'Giving a mark without naming the criterion that failed.',
    'Letting having taken part in the discussion bias the verdict.',
]}
WORDS['goal']['role_block'] = {}
LAYOUT['goal'].update({'done': '{text}', 'role_is': '{text}', 'role_may': '{items}', 'role_procedure': '{items}',
                      'role_patterns': '{items}', 'role_block': S.ROLE_BLOCK_LAYOUT})


def _summary(r, verdicts):
    """What a reading says, in the owner's words: names (D2), never counts."""
    where = '%s v%s' % (r.get('artifact'), r.get('v'))
    if not r.get('read'):
        return 'did not read %s: %s' % (where, r.get('why_not_read') or 'it was not read')
    left = ['%s %s' % (i, 'not met' if v == 'not_met' else 'to confirm') for i, v in verdicts.items() if v != 'met']
    held = 'every done-when item holds' + (', and something is noted' if r.get('findings') else '')
    return 'read %s: %s' % (where, ', '.join(left) if left else held)


def _entry(r):
    """One reading of the journal as the pane lists it: when, what it says, and the verdict of each done-when item."""
    verdicts = R.audit_verdicts(r.get('items'))
    return {'summary': _summary(r, verdicts), 'at': r.get('at'), 'artifact': r.get('artifact'), 'v': r.get('v'),
            'read': bool(r.get('read')), 'why_not_read': r.get('why_not_read'), 'verdicts': verdicts}


def _latest(rows):
    """The newest reading that read its version: one entry for each done-when item, the row whose verdict stands (when code
    and the reader disagreed, both rows are in the journal and the worse stands), and the findings it filed, a low or a
    medium one included, which ask the owner nothing and so show nowhere else; None when no version has been read."""
    r = next((x for x in reversed(rows) if x.get('read')), None)
    if r is None:
        return None
    verdicts, seen, items = R.audit_verdicts(r.get('items')), set(), []
    for row in r.get('items') or []:
        if row['id'] in seen or row['verdict'] != verdicts.get(row['id']):
            continue
        seen.add(row['id'])
        items.append({k: row[k] for k in ('id', 'verdict', 'method', 'evidence', 'claim')})
    return {'artifact': r['artifact'], 'v': r['v'], 'at': r.get('at'), 'items': items,
            'findings': [dict(f) for f in r.get('findings') or []]}


def _spot_entry(r):
    """One spot check of spot_checks.jsonl as the pane lists it: what it says, when, whether every check held, the checks and the
    findings it filed. Not the minute it fell on: Audit drops in unannounced."""
    found = [dict(f) for f in r.get('findings') or []]
    return {'summary': SPOT_SAYS[not found] + ('' if not found else ': ' + str(found[0].get('claim'))), 'at': r.get('at'), 'ok': not found,
            'checks': [dict(c) for c in r.get('checks') or []], 'findings': found}


def view(ref, d, events, asks):
    """Audit's pane (S.VIEWS['audit']): today's part, by reference, with the readings of readings.jsonl in place of the
    ledger's lines once any exists, each with its artifact, version, whether it was read and the verdict of each item, and
    `latest`: the newest version read, item by item, with the findings it filed (M8.3); and its spot checks, the last few of
    spot_checks.jsonl, oldest first (M8.7)."""
    part = dict(FV._j2_part(ref, d, 'Audit', events, asks))
    rows = W.rows(ref, 'readings.jsonl')
    if rows:
        part['readings'] = [_entry(r) for r in rows[-6:]]
    part['latest'] = _latest(rows)
    part['spot_checks'] = [_spot_entry(r) for r in W.rows(ref, 'spot_checks.jsonl')[-6:]]
    return FV._clean(part)
