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
filed and noted. A finding keeps the page's file name in `page` and `where` (the writer who puts it right needs it, and a link's
target is in `where`) and gives the owner's name for the page in `name`; its `claim` is quoted to the owner, so it names no file.
It is the engine_runtime body's superset: the legacy body stays there as the fallback a broken layer file leaves, and W3-PROOF
deletes it.
"""
import json
import posixpath
import re
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


def _defect(page, severity, element, claim, target=None):
    """One finding: where it is (`where`: the page and the element, and for a link where it goes, which the writer who puts it right
    needs), what is wrong (`claim`, which names the element too, so it reads alone, and names no file: it is quoted to the owner),
    and how serious. `page` is the page's own file name, which Identity maps to a title; audit_mechanical adds `name`, the title."""
    where = '%s: %s%s' % (page, element, (' (to %s)' % _clip(target, 80)) if target else '')
    return {'where': _clip(where, 200), 'page': _clip(page, 200), 'claim': _clip(claim, 600), 'severity': severity, 'kind': 'defect'}


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
                out.append(_defect(name, 'low', element, '%s goes to a part of the page that is not there' % element, '#' + _clip(frag)))
            continue
        target = posixpath.normpath(path.lstrip('/') if path.startswith('/') else posixpath.join(posixpath.dirname(name), path))
        target = 'index.html' if target in ('.', '') else target
        if not target.lower().endswith(('.html', '.htm')):
            continue                                             # a file that is not a page (a style, a picture) is not this check's
        if target not in planned:
            out.append(_defect(name, 'medium', element, '%s goes to a page the site does not have' % element, target))
        elif frag not in ('', 'top') and target in parsed and frag not in parsed[target].ids:
            out.append(_defect(name, 'low', element, '%s goes to a part of another page that is not there' % element,
                               '%s#%s' % (target, _clip(frag))))
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


def _hole(hole, names=None):
    """A placeholder where a fact should be, as the legacy body finds it (R.placeholders), with `where` added: the page and the
    words that say it, and `name`: what the owner calls the page (`names`, from _names). `page` stays the page's file name, which
    Identity's question to the owner is put by."""
    phrase = R.PLACEHOLDER.search(str(hole.get('claim') or ''))
    page = hole.get('page')
    return dict(hole, where=_clip("%s: the text '%s'" % (page, phrase.group(0) if phrase else 'to be confirmed'), 200),
                name=(names or {}).get(page, page))


def _note(defect, names=None):
    """A defect as the mechanical step's notes say it: the page by the name the owner knows it by (`names`, from _names; its file
    name when it has none), then what is wrong (the claim names the element). The finding itself keeps the page's file name in
    `page` and `where`, which is what Identity maps to a title and what the writer who puts it right needs."""
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
    names = _names(ref, files)
    # a page that says "to be confirmed" published what nobody knew (found live 2026-09-28: twelve such places on four
    # pages); Audit names each hole, Identity asks the owner for the facts instead of a stamp
    holes = [_hole(h, names) for h in R.placeholders(files)]
    defects = [dict(d, name=names.get(d['page'], d['page'])) for d in page_defects(files)]      # each says which page in the owner's words
    failing = [d for d in defects if d['severity'] != 'low']
    said = notes + (['the site says it does not know %d thing%s' % (len(holes), '' if len(holes) == 1 else 's')] if holes else [])
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


CODE = {
    'audit_pick': ref_to('audit_pick'),
    'audit_mechanical': audit_mechanical,
    'audit_file': ref_to('audit_file'),
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


def view(ref, d, events, asks):
    """Audit's pane (S.VIEWS['audit']): today's part, by reference, with the readings of readings.jsonl in place of the
    ledger's lines once any exists, each with its artifact, version, whether it was read and the verdict of each item, and
    `latest`: the newest version read, item by item, with the findings it filed (M8.3)."""
    part = dict(FV._j2_part(ref, d, 'Audit', events, asks))
    rows = W.rows(ref, 'readings.jsonl')
    if rows:
        part['readings'] = [_entry(r) for r in rows[-6:]]
    part['latest'] = _latest(rows)
    return FV._clean(part)
