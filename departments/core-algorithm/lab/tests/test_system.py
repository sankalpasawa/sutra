"""The page builder: a goal in words in, a small department folder with its page out (extensions/system.py, extensions/g2.py).
The tests of the version's claims (C1 to C10 in lab/README.md), of its stated limits where a test can pin one, and of the
should-fix findings of the refuter rounds on the earlier builds. Which test holds which claim:
  C1   the same inputs, the same bytes, one folder      test_website_words_become_a_ready_system_with_a_page, test_the_same_inputs_give_the_same_bytes_whatever_else_is_registered,
                                                        test_command_writes_one_folder_and_prints_one_line, test_one_folder_never_holds_two_systems,
                                                        test_another_pack_is_another_folder_and_another_system,
                                                        test_the_recorded_systems_are_what_the_builder_builds_and_the_command_writes
  C2   refusals: one line, exit code 2, nothing written test_command_refusals_are_one_line_and_write_nothing, test_one_folder_never_holds_two_systems,
       a call that wrote and did not end well: exit 3   test_a_call_that_wrote_ends_with_another_exit_code_than_a_refusal
  C3   the code behind every kind is on the record      test_every_function_behind_a_kind_is_on_the_record
  C4   a closed catalogue, and no guess                 test_guesses_nothing_without_a_chosen_domain, test_refuses_what_it_cannot_build, test_every_catalogue_and_exhibit_row_is_a_recorded_case
  C5   ready and waiting only after the whole path      test_the_yes_path_is_followed_to_its_end, test_ready_needs_a_well_formed_workflow_that_meets_the_standard,
                                                        test_another_route_than_the_plan_shown_is_not_waiting, test_an_effect_that_does_not_hold_is_not_ready
  C6   not ready says where; no plan is blocked         test_a_yes_that_does_not_get_there_is_not_waiting, test_a_step_the_kernel_recorded_as_stopped_is_shown_as_a_stop,
                                                        test_another_route_than_the_plan_shown_is_not_waiting, test_blocked_goal_says_where_and_why,
                                                        test_the_first_sentence_names_the_reason_the_kernel_names
  C7   both answers to each question                    test_order_words_wait_on_the_customer_and_show_both_answers, test_a_no_shows_what_the_kernel_did
  C8   the page                                         test_page_escapes_every_string_it_was_given, test_picture_has_a_box_per_step_and_arrows_that_cross_no_box,
                                                        test_sentences_fit_the_state, test_words_are_read_by_code_point, test_a_page_is_tags_and_text_and_nothing_else,
                                                        test_what_a_mutation_run_changed_on_a_page_unseen_is_held
  C9   the record beside the page, and the checks       test_record_json_holds_every_look_and_run_whole, test_the_system_says_of_a_look_only_what_its_chain_carries,
                                                        test_the_independent_checks_hold_the_record_and_refuse_forgeries, test_the_checks_work_every_system_and_page_out_again,
                                                        test_each_comparison_of_the_checks_is_the_one_that_refuses_its_own_forgeries
  C10  cases 70 and 71                                  test_every_catalogue_and_exhibit_row_is_a_recorded_case, test_a_yes_that_does_not_get_there_is_not_waiting,
                                                        test_the_first_sentence_names_the_reason_the_kernel_names, test_the_independent_checks_hold_the_record_and_refuse_forgeries
  limits pinned by a test: a write cut short (test_a_write_cut_short_holds_no_manifest_and_is_finished_by_the_next_run), steps run in another order after a tie
  (test_another_route_than_the_plan_shown_is_not_waiting), a step that rests on a condition that holds only through a rule (test_a_step_the_kernel_recorded_as_stopped_is_shown_as_a_stop),
  what a result says beside its trace (test_the_system_says_of_a_look_only_what_its_chain_carries).
The tests that read the built record (results/actual_run_records.json) run after tools/run_all.py, as the lab's README runs them; without a record they are skipped."""
from pathlib import Path
import unittest, sys, json, copy, hashlib, re, io, os, tempfile, contextlib, html, functools, importlib.util, ast
from html.parser import HTMLParser
import subprocess   # the command run as a process of its own (the limits pinned for the confirming round)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kernel.core import State, Kernel, digest, ACTIONS, register
from tools.run_all import CASES, pack
from extensions.asks import answer, open_asks
from extensions.reflection import Learner
import extensions.system as G
import extensions.g2 as g2

ASK = {'compute': 0, 'money': 0, 'attention': 1}
ROOTLESS = hasattr(os, 'geteuid') and os.geteuid() != 0   # a folder mode can only refuse someone who is not root, on a system that has such modes
WEBSITE = 'a website for my organisation'
ORDER = 'complete a customer order when the item is out of stock'
VERDICTS = ['READY', 'WAITING', 'READY', 'READY', 'NO_DOMAIN', 'NO_DOMAIN', 'BLOCKED', 'NOT_READY', 'NOT_READY', 'NOT_READY']
ALLOWED = {'html', 'head', 'meta', 'title', 'style', 'body', 'main', 'p', 'span', 'h1', 'h2', 'div', 'svg', 'path', 'polygon', 'g', 'rect', 'text', 'details', 'summary',
           'table', 'tr', 'th', 'td', 'code', 'pre', 'ul', 'ol', 'li', 'a', 'b', 'fieldset', 'legend', 'input', 'label', 'footer'}
ATTRS = {'lang', 'charset', 'name', 'content', 'class', 'viewbox', 'width', 'height', 'role', 'aria-label', 'd', 'points', 'x', 'y', 'rx', 'type', 'id', 'checked', 'for',
         'href', 'colspan'}   # as the interpreter's own parser names them (it lowers viewBox)
RECORD = ROOT / 'results' / 'actual_run_records.json'
MINE = ['S120_systems_whole_on_the_record', 'S121_every_look_and_run_behind_a_page_is_on_the_record', 'S122_systems_and_verdicts_follow_from_the_kernel_results',
        'S123_pages_are_what_this_file_renders_and_run_nothing', 'S124_no_guess_and_every_domain_a_recorded_case',
        'S125_the_command_writes_the_recorded_bytes_and_refuses_in_one_line', 'S126_case_70_waits_and_its_yes_does_not_get_there',
        'S128_case_71_waits_and_after_its_yes_the_page_names_the_reason_the_kernel_names', 'S127_system_claims_fail_on_forged_records']   # in the order the module returns them: the forgery row last
FORGERY_ROW = MINE[8]
PAGE_COUNT, SYSTEM_COUNT = 50, 107   # how many forgeries of S127 only the whole page, and only the whole system.json, refuse (test_each_comparison_of_the_checks_is_the_one_that_refuses_its_own_forgeries)
S201 = 'S201_recorded_sequences_are_the_scene_files_sealed_and_their_runs_agree_with_their_traces'   # the add-on base's own check: every run in a recorded sequence, by the rule of S42


def m(mid, effect, action='simulate_fact', cost=None, req=(), **kw):
    return dict(dict(id=mid, effect=effect, requires=list(req), provider='prov', grant='g', cost=dict(cost if cost is not None else {'compute': 1, 'money': 0, 'attention': 0}),
                     action=action, approved=True), **kw)


def world(goals, rules=(), methods=(), evidence=(), **kw):
    return dict({'schema': 'sutra-extension/2', 'id': 'w', 'goals': list(goals), 'rules': [{'id': 'R-' + h, 'head': h, 'branches': b, 'approved': True} for h, b in rules],
                 'methods': list(methods), 'evidence': list(evidence), 'providers': {'prov': 30}, 'grants': ['g']}, **kw)


def row(p, t='TRUE', **kw):
    return dict({'predicate': p, 'truth': t, 'verified': True, 'source': 'fx', 'version': '1'}, **kw)


def build(w, words='ship it', **more):
    """One world as a one-row catalogue, built by the page builder."""
    entry = dict({'id': 'w', 'title': 'W', 'goal': (w['goals'] or ['none'])[0], 'say': 'ship it', 'words': ['ship'], 'packs': ['w']}, **more)
    return G.build_system(words, [entry], lambda n: copy.deepcopy(w) if n == 'w' else pack(n))


def exhibit(i):
    r = g2.exhibits()[i]
    return G.build_system(r['say'], [r], pack, r['id'])


def with_kind(kind, change, make):
    """Build with one registered kind changed for the length of the build."""
    old = ACTIONS[kind]
    ACTIONS[kind] = change(old)
    try:
        return make()
    finally:
        ACTIONS[kind] = old


class Tags(HTMLParser):
    """Every tag, every attribute and every link of a page."""
    def __init__(self):
        super().__init__()
        self.names, self.attrs, self.hrefs = set(), [], []

    def handle_starttag(self, tag, attrs):
        self.names.add(tag)
        self.attrs += [(tag, k, v) for k, v in attrs]
        self.hrefs += [v for k, v in attrs if k == 'href']


def tags(page):
    t = Tags()
    t.feed(page)
    return t


def text(page):
    """What a reader sees, one block per line (tags gone, entities resolved)."""
    body = page[page.index('<body>'):]
    body = re.sub(r'</(p|h1|h2|li|tr|summary|legend|div|label|fieldset|details|table|footer|text|title)>', '\n', body)
    return '\n'.join(' '.join(line.split()) for line in html.unescape(re.sub(r'<[^>]+>', ' ', body)).split('\n') if line.strip())


def lead(s):
    return html.unescape(re.search(r'<p class="lead">(.*?)</p>', s['files']['index.html']).group(1))


def picture(page):
    """The boxes, the arrows (as points) and the arrow heads of the picture."""
    rects = [tuple(int(v) for v in r) for r in re.findall(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"', page)]
    paths = [[tuple(float(v) for v in pt.split(',')) for pt in re.findall(r'[ML]([0-9.]+,[0-9.]+)', d)] for d in re.findall(r'<path class="edge" d="([^"]*)"', page)]
    heads = [tuple(float(v) for v in h.split(',')) for h in re.findall(r'<polygon class="head" points="([0-9.]+,[0-9.]+) ', page)]
    return rects, paths, heads


def crossings(page):
    """The points of any arrow that lie inside a box (an arrow may only touch the edge of the boxes it joins)."""
    rects, paths, _ = picture(page)
    hit = []
    for pts in paths:
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            for i in range(41):
                px, py = x1 + (x2 - x1) * i / 40, y1 + (y2 - y1) * i / 40
                hit += [(px, py, r) for r in rects if r[0] < px < r[0] + r[2] and r[1] < py < r[1] + r[3]]
    return hit


def chain_ok(r):
    prev = 'GENESIS'
    for i, e in enumerate(r['trace']):
        if e['seq'] != i + 1 or e['prev_sha256'] != prev or e['sha256'] != digest({k: v for k, v in e.items() if k != 'sha256'}):
            return False
        prev = e['sha256']
    return r['trace_root_sha256'] == prev


def file_sha(rel):
    return hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()


def recorded():
    """The record tools/run_all.py wrote before the tests ran (None when it is not there or is older than this version)."""
    if not RECORD.exists():
        return None
    data = json.loads(RECORD.read_text(encoding='utf-8'))
    return data if 'system' in data.get('scenes', {}) else None


def scene():
    """The recorded sequence, run again as tools/run_all.py runs it."""
    path, ns = ROOT / 'tools' / 'scenes' / 'system.py', {}
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), ns)
    return ns['scene']({'State': State, 'Kernel': Kernel, 'pack': pack, 'answer': answer, 'open_asks': open_asks, 'Learner': Learner, 'digest': digest})


def verifier():
    """The independent verifier, loaded from its file (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location('independent_verify_for_system_tests', ROOT / 'qa' / 'independent_verify.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_module():
    """The independent checks of this version, loaded as the verifier loads them."""
    path, ns = ROOT / 'qa' / 'checks' / 'system.py', {}
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), ns)
    return ns


class PageBuilderTests(unittest.TestCase):
    maxDiff = None

    # ---------------------------------------------------------------- C1, C2, C3: one command, one folder, the same bytes; refusals; the code on the record
    def test_website_words_become_a_ready_system_with_a_page(self):
        a = g2.build(WEBSITE)
        self.assertEqual((a['verdict'], a['domain']['id'], a['kinds'], a['status'], a['schema']),
                         ('READY', 'website', ['ask', 'compile_candidate', 'emit_artifact', 'simulate_fact'], 'PROPOSED_ONLY', 'core-algorithm/system/4'))
        self.assertEqual(a['choice']['ranking'][0], {'domain': 'website', 'shared_words': 2, 'words': ['organisation', 'website']})
        wf, run = a['implementation']['workflow'], a['model_run']
        self.assertEqual([s['method'] for s in wf['steps'] if s.get('method')], ['plan-site@1', 'write-content@1', 'build-pages@1', 'check-site@1'])
        self.assertEqual((a['workflow_problems'], a['blocked_at'], [r['status'] for r in run['path']], run['asks'], run['effects_missing'], run['goal_held'], run['after']['status'], run['after']['actions']),
                         ([], [], ['LOCAL_MODEL_EFFECTS_RECORDED'], [], [], True, 'PLAN_READY', []))
        st = a['standard']
        self.assertEqual((st['registrable'], st['status'], st['workflow'], [c['truth'] for c in st['checks']]), (True, 'SUPPORTED_BY_EVIDENCE', 'W-site-live', ['TRUE'] * 3))
        self.assertEqual((a['file_names'], sorted(a['files'])), (G.BUILT_FILES, sorted(G.BUILT_FILES)))   # a closed list of names: none comes from a pack or from the words
        self.assertEqual(a['system_sha256'], digest({k: v for k, v in a.items() if k not in ('files', 'files_sha256', 'system_sha256', 'folder')}))
        self.assertEqual({n: hashlib.sha256(t.encode()).hexdigest() for n, t in a['files'].items()}, a['files_sha256'])   # what shasum prints for each written file
        self.assertEqual(json.loads(a['files']['manifest.json']), {'schema': 'core-algorithm/system-manifest/1', 'system_sha256': a['system_sha256'],
                                                                   'files': {n: h for n, h in a['files_sha256'].items() if n != 'manifest.json'}})
        self.assertEqual((json.loads(a['files']['workflow.json']), json.loads(a['files']['atoms.json']), json.loads(a['files']['scaffold.json'])),
                         (wf, a['implementation']['atoms'], a['implementation']['scaffold']))
        self.assertEqual(json.loads(a['files']['system.json']), {k: v for k, v in a.items() if k not in ('files', 'files_sha256', 'folder')})
        self.assertEqual(a['folder'], 'a-website-for-my-organisation-' + a['files_sha256']['manifest.json'][:16])   # named after the manifest, which lists the digest of every other file
        self.assertEqual(a['pack_digests'], {'domain': [{'pack': n, 'sha256': digest(pack(n))} for n in a['domain']['packs']], 'standard': [{'pack': n, 'sha256': digest(pack(n))} for n in G.STANDARD]})
        page = a['files']['index.html']
        self.assertEqual(lead(a), 'Ready: 4 steps in order, and nothing waits on anyone.')
        for words in ('<span class="tag">Proposal only</span><span class="tag">Ready</span>', f'<h1>{WEBSITE}</h1>', f'<title>{WEBSITE}</title>', '<div class="verdict READY">',
                      'These 4 steps, in this order, make it true that the website is live.', 'PROPOSED_ONLY: nothing on this page has run outside a local model, and running a step for real is outside this lab.',
                      'Built from the reviewed domain <b>Website</b>, chosen by a word match on organisation, website (a stand-in: a person or an agent should confirm the choice).',
                      f'System sha256 <code>{a["system_sha256"]}</code>; the digest of every other file written beside this page is in manifest.json.',
                      '<h2>What done means</h2><ul><li>The site has been checked</li></ul>', 'Who may do what: 4 steps have their grant',
                      'The workflow generated on this page has the parts the standard asks for: yes, 3 of 3',
                      'This is about the shape of the workflow written below, not about the goal above.', 'The workflow, step by step: 4 method steps, between a step that records the goal and a step that shows the result',
                      'A run in the local model: the plan ran through, and the goal is held', 'Nothing real happened: each receipt is marked local only.',
                      '<a href="record.json">record.json</a>', '<a href="workflow.json">workflow.json</a>'):
            self.assertIn(words, page)
        self.assertLess(page.index('stand-in'), page.index('<h2>The plan</h2>'))   # who chose is said on the first screen, not only in the footer
        self.assertEqual(sorted(set(tags(page).hrefs)), sorted(n for n in a['file_names'] if n != 'index.html'))

    def test_the_same_inputs_give_the_same_bytes_whatever_else_is_registered(self):
        before = sorted(str(p) for p in ROOT.rglob('*') if '__pycache__' not in p.parts)
        a = g2.build(WEBSITE)
        register('test_other_kind')(lambda s, mm, mid, deps: {})
        try:
            b = g2.build(WEBSITE)
        finally:
            del ACTIONS['test_other_kind']
        self.assertEqual((a['system_sha256'], a['files'], a['folder']), (b['system_sha256'], b['files'], b['folder']))   # whatever else the process has registered
        self.assertEqual(before, sorted(str(p) for p in ROOT.rglob('*') if '__pycache__' not in p.parts))                # building writes nothing
        rows, packs = g2.catalogue(), {n: pack(n) for r in g2.catalogue() for n in r['packs'] + list(G.STANDARD)}
        kept = copy.deepcopy((rows, packs))
        c = G.build_system(WEBSITE, rows, lambda n: packs[n])
        self.assertEqual((c['files'], (rows, packs)), (a['files'], kept))   # the caller's catalogue and packs are read, not changed

    def test_every_function_behind_a_kind_is_on_the_record(self):
        # Refuter round one on the second build: only the handler's module and file were recorded, so a hook, a wrapper or a handler of the same file left the record as it was.
        a, o = g2.build(WEBSITE), g2.build(ORDER)
        one = lambda fn, rel: {'function': fn, 'file': rel, 'sha256': file_sha(rel)}
        self.assertEqual(a['handlers'], {'ask': {h: one(f, 'extensions/asks.py') for h, f in (('check', '_check'), ('plan', '_plan'), ('run', 'ask'), ('settle', '_settle'))},
                                         'compile_candidate': {'run': one('compile_candidate', 'extensions/constructor.py')}, 'emit_artifact': {'run': one('emit_artifact', 'extensions/constructor.py')},
                                         'simulate_fact': {'run': one('_simulate_fact', 'kernel/core.py')}})
        self.assertEqual(a['handlers'], o['handlers'])
        here = lambda fn: one(fn, 'tests/test_system.py')
        c = with_kind('emit_artifact', lambda old: dict(old, run=lambda s, mm, mid, deps: {}), lambda: g2.build(WEBSITE))   # another handler is another system, and the record says which
        self.assertEqual(c['handlers']['emit_artifact'], {'run': here('<lambda>')})
        self.assertNotEqual(c['system_sha256'], a['system_sha256'])
        b = with_kind('ask', lambda old: dict(old, settle=lambda s, r, log: None), lambda: g2.build(ORDER))   # another hook: the verdict changes, and so does the record
        self.assertEqual((o['verdict'], b['verdict'], b['handlers']['ask']['settle'], b['handlers']['ask']['run']), ('WAITING', 'NOT_READY', here('<lambda>'), o['handlers']['ask']['run']))
        self.assertNotEqual(b['system_sha256'], o['system_sha256'])
        calls = []
        def logged(fn):   # a wrapper that takes the handler's name and module: its code is still its own
            @functools.wraps(fn)
            def run(*x):
                calls.append(1)
                return fn(*x)
            return run
        w = with_kind('simulate_fact', lambda old: dict(old, run=logged(old['run'])), lambda: g2.build(WEBSITE))
        self.assertEqual((w['verdict'], w['handlers']['simulate_fact'], bool(calls)), ('READY', {'run': here('run')}, True))
        self.assertNotEqual(w['system_sha256'], a['system_sha256'])
        x = with_kind('emit_artifact', lambda old: dict(old, run=ACTIONS['compile_candidate']['run']), lambda: g2.build(WEBSITE))   # the handler of another kind, from the same file
        self.assertEqual(x['handlers']['emit_artifact'], {'run': one('compile_candidate', 'extensions/constructor.py')})
        self.assertNotEqual(x['system_sha256'], a['system_sha256'])
        self.assertEqual(G._code(len), {'function': 'builtin_function_or_method', 'file': None, 'sha256': None})   # code with no source file is recorded as that
        self.assertEqual((g2.build(WEBSITE)['system_sha256'], g2.build(ORDER)['system_sha256']), (a['system_sha256'], o['system_sha256']))

    def test_the_recorded_systems_are_what_the_builder_builds_and_the_command_writes(self):
        data = recorded()
        if data is None:
            self.skipTest('results/actual_run_records.json is generated by tools/run_all.py')
        fresh, built = scene(), g2.demo()
        self.assertEqual(json.dumps(fresh, ensure_ascii=False, sort_keys=True), json.dumps(data['scenes']['system'], ensure_ascii=False, sort_keys=True))
        self.assertEqual(([s['verdict'] for s in built], sorted(fresh), len(set(s['folder'] for s in built))), (VERDICTS, ['command', 'schema', 'systems'], 10))
        self.assertEqual([{'folder': s['folder'], 'files': s['files']} for s in built], [{'folder': e['folder'], 'files': e['files']} for e in fresh['systems']])
        for s, e in zip(built, fresh['systems']):
            rec = json.loads(s['files']['record.json'])
            self.assertEqual(e.get('looks'), None if 'draft' in rec else {'runs': G.looks(rec)}, s['asked'])
        def parts(v):   # every dict of the sequence, wherever it sits
            if type(v) is dict:
                yield v
                for x in v.values():
                    yield from parts(x)
            elif type(v) is list:
                for x in v:
                    yield from parts(x)
        tree = ast.parse((ROOT / 'tools' / 'scenes' / 'system.py').read_text(encoding='utf-8'))
        stated = [(n.targets[0].id, ast.literal_eval(n.value)) for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and getattr(n.targets[0], 'id', '') in ('LOOKS', 'RUNS')]
        found = list(parts(data['scenes']['system']))   # the scene file states, once each, the number of looks (a dict holding a list under runs) and of runs (a dict with a trace and its root)
        self.assertEqual(stated, [('LOOKS', sum(type(x.get('runs')) is list for x in found)), ('RUNS', sum('trace' in x and 'trace_root_sha256' in x for x in found))])
        self.assertEqual(stated, [('LOOKS', 8), ('RUNS', 30)])
        with tempfile.TemporaryDirectory() as t:   # and the command writes exactly these bytes, one folder per system
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(g2.main(['--demo', '--out', t]), 0)
            self.assertEqual({d.name: {p.name: p.read_bytes().decode('utf-8') for p in d.iterdir()} for d in Path(t).iterdir()}, {e['folder']: e['files'] for e in fresh['systems']})
        first, wrote = built[0], fresh['command']
        want = {first['folder'] + '/' + n: h for n, h in first['files_sha256'].items()}
        self.assertEqual([(c['exit'], c['written'] == want) for c in wrote], [(0, True), (0, True), (2, False), (2, False), (3, True)])
        self.assertEqual([c['stderr'] for c in wrote[2:]], [[f'g2.py: error: <out>/{first["folder"]} already holds something that is not this system (notes.txt): nothing was written'],
                                                           ['g2.py: error: Unknown domain: pick one from the catalogue'],
                                                           ['g2.py: error: 1 of 1 folders were written under <out>, and the line that says so could not be printed (BrokenPipeError)']])
        self.assertEqual((wrote[2]['written'], wrote[4]['stdout']), (wrote[3]['written'], []))

    def test_command_writes_one_folder_and_prints_one_line(self):
        s = g2.build(WEBSITE)
        listed = lambda d: sorted(p.name for p in Path(d).iterdir()) if Path(d).exists() else None
        inside = lambda: sorted(str(p) for p in ROOT.rglob('*') if '__pycache__' not in p.parts)
        before = inside()
        with tempfile.TemporaryDirectory() as t:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = g2.main(WEBSITE.split() + ['--out', t])
            d = Path(t).resolve() / s['folder']
            self.assertEqual((code, out.getvalue()), (0, f'READY      {WEBSITE}  ->  {d}/index.html\n'))
            self.assertEqual((listed(t), listed(d)), ([s['folder']], sorted(s['file_names'])))
            self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in d.iterdir()}, s['files_sha256'])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = g2.main(['ship', 'the', 'order', '--domain', 'website', '--out', t])   # the caller picks the domain
            self.assertEqual((code, out.getvalue().split()[0], len(listed(t))), (0, 'READY', 2))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = g2.main(['--list'])
            self.assertEqual((code, [line.split()[0] for line in out.getvalue().splitlines()]), (0, [r['id'] for r in g2.catalogue()]))
            self.assertIn('say: a website for my organisation', out.getvalue())
            out, demo = io.StringIO(), Path(t) / 'demo'
            with contextlib.redirect_stdout(out):
                code = g2.main(['--demo', '--out', str(demo)])
            self.assertEqual((code, [line.split()[0] for line in out.getvalue().splitlines()], len(listed(demo))), (0, VERDICTS, 10))
            keep = g2.BUILT   # without --out a build lands in results/built: here that default is pointed into the temporary folder
            self.assertEqual(keep, ROOT / 'results' / 'built')
            g2.BUILT = Path(t) / 'mine'
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(g2.main(['a', 'site']), 0)
            finally:
                g2.BUILT = keep
            self.assertEqual(len(listed(Path(t) / 'mine')), 1)
        self.assertEqual(inside(), before)   # nothing was written into the lab: the record the verifier reads is as it was
        for rel in ('qa/independent_verify.py', 'qa/checks/system.py'):   # and the folder a build lands in by default is no place the verifier reads: it compares no folder at all
            self.assertEqual(re.findall(r"['\"/]built['\"/]", (ROOT / rel).read_text(encoding='utf-8')), [], rel)

    def test_command_refusals_are_one_line_and_write_nothing(self):
        def fails(argv):
            err, out = io.StringIO(), io.StringIO()
            with self.assertRaises(SystemExit) as stop, contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                g2.main(argv)
            lines = err.getvalue().splitlines()
            self.assertEqual((stop.exception.code, len(lines), out.getvalue()), (2, 1, ''), (argv, err.getvalue()))   # one line, no usage block, nothing on standard output
            self.assertTrue(lines[0].startswith('g2.py: error: ') and 'Traceback' not in lines[0], (argv, lines))
            return lines[0]
        with tempfile.TemporaryDirectory() as t:
            a_file = Path(t) / 'a-file'
            a_file.write_text('x')
            for argv in ([], ['--out', t], ['a site', '--domain'], ['a site', '--nope'], ['a site', '--domain', 'nobody-reviewed-this', '--out', t], ['a site', '--domain', 'x\ny', '--out', t],
                         ['?!', '--out', t], ['\u3164\u3164', '--out', t], ['\U000e0100\U000e0101', '--out', t], ['\u180b\u180c', '--out', t], ['\U0001d173', '--out', t],
                         ['--list', 'words'], ['--demo', '--domain', 'order'], ['--list', '--demo'], ['--demo', 'my own words', '--out', t], ['a site', '--out', ''],
                         ['a site', '--out', str(a_file)], ['a site', '--out', 'x\x00y']):
                fails(argv)
            self.assertEqual(fails(['a site', '--domain', 'nobody-reviewed-this', '--out', t]), 'g2.py: error: Unknown domain: pick one from the catalogue')
            if ROOTLESS:   # a folder that cannot be written is one line too
                locked = Path(t) / 'locked'
                locked.mkdir()
                os.chmod(locked, 0o500)
                try:
                    fails(['a site', '--out', str(locked / 'deeper')])
                    fails(['a site', '--out', str(locked)])
                finally:
                    os.chmod(locked, 0o700)
            rows, keep = g2.catalogue(), g2.load_pack   # a damaged catalogue or pack file is one line as well, for a build and for --list alike
            deep = lambda n: json.loads('[' * 100000)
            for broken in ([dict(rows[0], title=['x'])], [{k: v for k, v in rows[0].items() if k != 'say'}], {'website': rows[0]}, 'x', None, rows + [rows[0]]):
                g2.load_pack = lambda n, b=broken: {'schema': 'sutra-extension/2', 'id': n, 'domains': b} if n == g2.CATALOGUE else keep(n)
                try:
                    fails(['--list'])
                    fails(['a site', '--out', t])
                finally:
                    g2.load_pack = keep
            for loader in (deep, lambda n: [], lambda n: None, lambda n: deep(n) if n != g2.CATALOGUE else keep(n), lambda n: [] if n != g2.CATALOGUE else keep(n)):
                g2.load_pack = loader
                try:
                    fails(['a site', '--out', t])
                finally:
                    g2.load_pack = keep
            self.assertEqual(sorted(p.name for p in Path(t).iterdir()), ['a-file'] + (['locked'] if ROOTLESS else []))   # nothing was written by a refused call
            fifth, many = g2.demo()[4], Path(t) / 'many'   # several systems asked for, and the folder of the fifth holds a stranger's file: every folder is looked at first, and none is written
            (many / fifth['folder']).mkdir(parents=True)
            (many / fifth['folder'] / 'notes.txt').write_text('mine')
            self.assertIn('(notes.txt): nothing was written', fails(['--demo', '--out', str(many)]))
            self.assertEqual(([p.name for p in many.iterdir()], [p.name for p in (many / fifth['folder']).iterdir()]), ([fifth['folder']], ['notes.txt']))
            site, odd = g2.build('a site'), Path(t) / 'odd'   # a stranger's file whose name holds a line break: the refusal names it and is still one line
            (odd / site['folder']).mkdir(parents=True)
            try:
                (odd / site['folder'] / 'two\nlines.txt').write_text('mine')
            except OSError:
                pass   # this machine takes no such file name
            else:
                self.assertEqual(fails(['a site', '--out', str(odd)]), f'g2.py: error: {odd.resolve() / site["folder"]} already holds something that is not this system (two lines.txt): nothing was written')
            if ROOTLESS:   # the system's own folder is there and cannot be read: looking into it is refused in one line, before anything is written (a mutation run found this unheld)
                shut = Path(t) / 'shut' / site['folder']
                shut.mkdir(parents=True)
                os.chmod(shut, 0o300)
                try:
                    self.assertIn('Permission denied', fails(['a site', '--out', str(shut.parent)]))
                finally:
                    os.chmod(shut, 0o700)
                self.assertEqual(list(shut.iterdir()), [])

    def test_one_folder_never_holds_two_systems(self):
        on_disk = lambda f: {p.name: p.read_bytes() for p in f.iterdir()}
        with tempfile.TemporaryDirectory() as out:
            a, b = g2.build('ship the order', 'order'), g2.build('ship the order', 'website')
            mine = {n: t.encode('utf-8') for n, t in a['files'].items()}
            folders = [g2.write(s, out) for s in (a, b, a)]
            self.assertEqual(len({f.name for f in folders}), 2)   # another domain for the same words is another folder; writing the same system twice is one folder
            self.assertTrue(all(f.parent == Path(out) for f in folders))
            for s, f in ((a, folders[0]), (b, folders[1])):
                self.assertEqual(on_disk(f), {n: t.encode('utf-8') for n, t in s['files'].items()})
                self.assertEqual(s['folder'], 'ship-the-order-' + s['files_sha256']['manifest.json'][:16])
            home = folders[0]
            def refused(why, system=a):
                with self.assertRaises(ValueError, msg=why) as stop:
                    g2.write(system, out)
                self.assertIn('nothing was written', str(stop.exception), why)
            refused('two systems whose folder names collide: the second is refused and the first stays whole', dict(b, folder=a['folder']))
            self.assertEqual(on_disk(home), mine)
            for name, put in (('notes.txt', lambda p: p.write_text('mine')), ('.hidden', lambda p: p.write_text('x')), ('sub', lambda p: p.mkdir())):
                put(home / name)
                refused('a folder that holds what is not the system\'s is not written into: ' + name)
                (home / name).rmdir() if name == 'sub' else (home / name).unlink()
            (home / '.DS_Store').write_bytes(b'x')   # what a file browser leaves behind does not count
            self.assertEqual(g2.write(a, out), home)
            (home / '.DS_Store').unlink()
            (home / 'manifest.json').write_text('{}')
            refused('a manifest that is not this system\'s')
            (home / 'index.html').write_bytes(mine['index.html'][:100])
            (home / 'manifest.json').write_bytes(mine['manifest.json'])
            refused('a file of the right name that was cut short is not this system\'s file')
            (home / 'index.html').write_bytes(mine['index.html'][:-1] + b'!')
            refused('a file of the right name and length with one other byte is not this system\'s file')
            (home / 'index.html').write_bytes(mine['index.html'])
            (home / 'manifest.json').unlink()   # a write that was cut short before its last files: the rest is byte-equal, so the next run finishes it
            (home / 'record.json').unlink()
            self.assertEqual((g2.write(a, out), on_disk(home)), (home, mine))
            target = Path(out) / 'notes-elsewhere.txt'   # a link inside the folder is never written through (refuter round one, a note)
            target.write_text('mine')
            (home / 'index.html').unlink()
            try:
                (home / 'index.html').symlink_to(target)
            except OSError:
                pass   # this machine makes no links
            else:
                refused('a link inside the folder')
                self.assertEqual(target.read_text(), 'mine')
                target.write_bytes(mine['index.html'])
                refused('a link inside the folder is refused also when it leads to the very bytes of this system\'s file')
                (home / 'index.html').unlink()
            self.assertEqual((g2.write(a, out), on_disk(home)), (home, mine))
            c, elsewhere = g2.build('a site'), Path(out) / 'elsewhere'
            elsewhere.mkdir()
            try:
                (Path(out) / c['folder']).symlink_to(elsewhere, target_is_directory=True)
            except OSError:
                pass
            else:
                refused('a link in the folder\'s place is not followed', c)
            self.assertEqual(list(elsewhere.iterdir()), [])
            d = g2.build('a web page')
            (Path(out) / d['folder']).write_text('x')
            refused('a file in the folder\'s place', d)
            e = g2.build('pages online')
            (Path(out) / e['folder']).mkdir()   # an empty folder of that name is taken
            self.assertEqual(sorted(p.name for p in g2.write(e, out).iterdir()), sorted(e['file_names']))
        long = ['please make something for the people who come to see us at the autumn fair, a ' + w for w in ('website', 'newsletter')]
        x, y = g2.build(long[0]), g2.build(long[1])
        self.assertEqual((x['folder'][:41], y['folder'][:41]), ('please-make-something-for-the-people-who-',) * 2)
        self.assertNotEqual(x['folder'], y['folder'])
        risky = world(['../../etc/passwd'], methods=[m('rm -rf /', '../../etc/passwd')])   # no name from a pack or from the words becomes a file or a folder name
        names = G.build_system('../../etc/passwd', [{'id': 'w', 'title': 'W', 'goal': '../../etc/passwd', 'say': 'x', 'words': ['x'], 'packs': ['w']}], lambda n: risky if n == 'w' else pack(n), 'w')
        self.assertEqual((names['verdict'], names['file_names'], sorted(names['files']), names['folder']), ('READY', G.BUILT_FILES, sorted(G.BUILT_FILES), 'etc-passwd-' + names['files_sha256']['manifest.json'][:16]))

    def test_another_pack_is_another_folder_and_another_system(self):
        # Refuter round on the third build: the folder was named after the system's digest, and the system did not hold the packs' bytes: a row added to a pack gave another
        # record.json under the same folder name and the same digest on the page. The system now records every pack by its digest, and the folder is named after the manifest.
        rows = g2.catalogue()
        for name, words in (('72_site_methods', WEBSITE), ('02_methods', ORDER), ('22_enquiry_methods', 'answer and store customer enquiries'), ('63_repair_method', 'check a workflow against the standard')):
            def other(n, name=name):
                p = copy.deepcopy(pack(n))
                if n == name:
                    p.setdefault('evidence', []).append(row('office_painted', source='fixture/other'))   # a fact no plan reads: the kernel's looks and runs stay as they were
                return p
            a, b = G.build_system(words, rows, pack), G.build_system(words, rows, other)
            self.assertEqual((a['verdict'], a['plan']['trace_root_sha256']), (b['verdict'], b['plan']['trace_root_sha256']), words)
            self.assertNotEqual(a['pack_digests'], b['pack_digests'], words)
            self.assertNotEqual((a['system_sha256'], a['folder']), (b['system_sha256'], b['folder']), words)
            self.assertTrue(a['system_sha256'] != b['system_sha256'] and a['folder'] != b['folder'], words)
        def other_standard(n):   # the two packs of the workflow standard are on the record as well
            p = copy.deepcopy(pack(n))
            if n == G.STANDARD[1]:
                p['rules'][0]['source'] = 'reviewed/elsewhere'
            return p
        a, c = G.build_system(WEBSITE, rows, pack), G.build_system(WEBSITE, rows, other_standard)
        self.assertEqual((a['standard']['trace_root_sha256'], a['pack_digests']['domain']), (c['standard']['trace_root_sha256'], c['pack_digests']['domain']))
        self.assertTrue(a['pack_digests']['standard'] != c['pack_digests']['standard'] and a['system_sha256'] != c['system_sha256'] and a['folder'] != c['folder'])
        keep = G._page   # and whatever differs in any file is another folder, also where the system is the same: the name stands for the bytes
        G._page = lambda system, record: keep(system, record).replace('<h2>Files</h2>', '<h2>The files</h2>')
        try:
            d = G.build_system(WEBSITE, rows, pack)
        finally:
            G._page = keep
        self.assertEqual((d['system_sha256'], d['files']['system.json'], d['files']['record.json']), (a['system_sha256'], a['files']['system.json'], a['files']['record.json']))
        self.assertNotEqual(d['folder'], a['folder'])
        self.assertEqual([d['folder'][-16:], a['folder'][-16:]], [hashlib.sha256(x['files']['manifest.json'].encode()).hexdigest()[:16] for x in (d, a)])

    def test_a_call_that_wrote_ends_with_another_exit_code_than_a_refusal(self):
        # Refuter round on the third build: a line that could not be printed after a completed write ended like a refusal (one line, exit code 2), although the claim
        # says a refusal writes nothing. Exit code 2 now means that this call did not touch the disk; a call that wrote and did not end well is exit code 3.
        def call(argv, stdout=None):
            out, err = stdout or io.StringIO(), io.StringIO()
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = g2.main(argv)
            except SystemExit as stop:
                code = stop.code
            return code, out, err.getvalue()
        class Closed(io.StringIO):
            def write(self, text):
                raise BrokenPipeError(32, 'Broken pipe')
        on_disk = lambda f: {q.name: q.read_bytes().decode('utf-8') for q in f.iterdir()}
        with tempfile.TemporaryDirectory() as t:
            t = Path(t).resolve()
            s, raw = g2.build('ein B\u00fcro mit website'), io.BytesIO()   # an ASCII terminal: the line is printed with the character it cannot encode as an escape, and the call ends well
            narrow = io.TextIOWrapper(raw, encoding='ascii', errors='strict')
            code, _, err = call(['ein', 'B\u00fcro', 'mit', 'website', '--out', str(t / 'a')], narrow)
            narrow.flush()
            self.assertEqual((code, err, raw.getvalue().decode('ascii')), (0, '', f'READY      ein B\\xfcro mit website  ->  {t / "a" / s["folder"]}/index.html\n'))
            self.assertEqual(on_disk(t / 'a' / s['folder']), s['files'])
            site = g2.build(WEBSITE)   # a standard output that takes no line: everything is written, one line on standard error says so, and the exit code is not a refusal's
            code, out, err = call(WEBSITE.split() + ['--out', str(t / 'b')], Closed())
            self.assertEqual((code, out.getvalue(), err), (3, '', f'g2.py: error: 1 of 1 folders were written under {t / "b"}, and the line that says so could not be printed (BrokenPipeError)\n'))
            self.assertEqual(on_disk(t / 'b' / site['folder']), site['files'])
            class Gone(io.StringIO):   # a pipe whose reader has gone, buffered: the line is taken, and sending it on fails (a mutation run found this unheld)
                sent = 0
                def flush(self):
                    self.sent += 1
                    if self.sent == 1:
                        raise BrokenPipeError(32, 'Broken pipe')
            code, out, err = call(WEBSITE.split() + ['--out', str(t / 'f')], Gone())
            self.assertEqual((code, err), (3, f'g2.py: error: 1 of 1 folders were written under {t / "f"}, and the line that says so could not be printed (BrokenPipeError)\n'))
            self.assertEqual(on_disk(t / 'f' / site['folder']), site['files'])
            code, out, err = call(['--list'], Closed())   # nothing is written by --list: a line that cannot be printed there is a refusal
            self.assertEqual((code, err.count('\n'), err.startswith('g2.py: error: ')), (2, 1, True))
            real = Path.write_bytes   # the disk fails while the files are being written: one line, exit code 3, and the next run finishes the folder
            def failing(path, data):
                if path.name == 'record.json':
                    raise OSError(28, 'No space left on device')
                return real(path, data)
            Path.write_bytes = failing
            try:
                code, out, err = call(WEBSITE.split() + ['--out', str(t / 'c')])
            finally:
                Path.write_bytes = real
            self.assertEqual((code, out.getvalue(), err.count('\n')), (3, '', 1))
            self.assertTrue(err.startswith(f'g2.py: error: stopped while writing, after 0 of 1 folders under {t / "c"} (OSError: ') and 'Traceback' not in err, err)
            self.assertEqual(sorted(on_disk(t / 'c' / site['folder'])), ['atoms.json', 'index.html'])   # what was written before the disk failed; no manifest
            code, out, err = call(WEBSITE.split() + ['--out', str(t / 'c')])
            self.assertEqual((code, err, on_disk(t / 'c' / site['folder'])), (0, '', site['files']))
            keep, looked = g2.check, []   # a stranger's file appears between the look at the folder and the write: the folder is looked at once more, and this call touches nothing
            def racing(system, out):
                d = keep(system, out)
                looked.append(d)
                if len(looked) == 1:
                    d.mkdir(parents=True)
                    (d / 'notes.txt').write_text('mine')
                return d
            g2.check = racing
            try:
                code, out, err = call(WEBSITE.split() + ['--out', str(t / 'd')])
            finally:
                g2.check = keep
            self.assertEqual((code, out.getvalue(), err), (2, '', f'g2.py: error: {t / "d" / site["folder"]} already holds something that is not this system (notes.txt): nothing was written\n'))
            self.assertEqual(on_disk(t / 'd' / site['folder']), {'notes.txt': 'mine'})
            calls = []   # several systems asked for, and the disk fails at the second: the line says how many folders are whole
            def second_fails(path, data):
                calls.append(path.parent.name)
                if len(set(calls)) == 2:
                    raise OSError(28, 'No space left on device')
                return real(path, data)
            Path.write_bytes = second_fails
            try:
                code, out, err = call(['--demo', '--out', str(t / 'e')])
            finally:
                Path.write_bytes = real
            self.assertEqual((code, out.getvalue(), err.count('\n'), err.startswith(f'g2.py: error: stopped while writing, after 1 of 10 folders under {t / "e"} (OSError: ')), (3, '', 1, True))
        self.assertEqual(Path.write_bytes, real)

    def test_a_write_cut_short_holds_no_manifest_and_is_finished_by_the_next_run(self):
        # A stated limit, pinned: a disk that fails while the files are being written leaves a folder half written. The manifest is written last, so a folder
        # that holds it holds every file it names; and what was written is this system's own bytes, so the next run finishes the folder.
        s, real = g2.build(WEBSITE), Path.write_bytes
        mine = {n: t.encode('utf-8') for n, t in s['files'].items()}
        for whole in range(len(mine)):   # the disk fails at the first file, at the second, ... at the last
            with tempfile.TemporaryDirectory() as out:
                written = []
                def failing(path, data):
                    if len(written) == whole:
                        raise OSError(28, 'No space left on device')
                    written.append(path.name)
                    return real(path, data)
                Path.write_bytes = failing
                try:
                    with self.assertRaises(OSError):
                        g2.write(s, out)
                finally:
                    Path.write_bytes = real
                home = Path(out) / s['folder']
                self.assertEqual((sorted(p.name for p in home.iterdir()), 'manifest.json' in written), (sorted(written), False), whole)
                self.assertEqual((g2.write(s, out), {p.name: p.read_bytes() for p in home.iterdir()}), (home, mine), whole)
        self.assertEqual(Path.write_bytes, real)

    # ---------------------------------------------------------------- C4: the choice of a domain
    def test_guesses_nothing_without_a_chosen_domain(self):
        s = g2.build('a weekly newsletter for my donors')
        self.assertEqual((s['verdict'], s['choice']['domain'], s['choice']['tied'], s['draft']['kernel_status']), ('NO_DOMAIN', None, [], 'SEMANTICS_UNAPPROVED'))
        self.assertFalse(s['draft']['pack']['rules'][0]['approved'])
        self.assertNotIn('implementation', s)
        self.assertEqual((s['file_names'], sorted(s['files'])), (G.DRAFT_FILES, sorted(G.DRAFT_FILES)))
        self.assertEqual(json.loads(s['files']['draft-pack.json']), s['draft']['pack'])
        self.assertIn('<pre>{\n  &quot;schema&quot;: &quot;sutra-extension/2&quot;,\n  &quot;id&quot;: &quot;draft-a-weekly-newsletter-for-my-donors&quot;,', s['files']['index.html'])   # the draft is shown as text, escaped like every other string
        look = json.loads(s['files']['record.json'])['draft']
        self.assertEqual((look['status'], look['trace_root_sha256'], chain_ok(look)), ('SEMANTICS_UNAPPROVED', s['draft']['trace_root_sha256'], True))
        page = s['files']['index.html']
        self.assertEqual(lead(s), 'No reviewed domain shares a word with these words, so nothing was guessed. Below is what someone has to write down first.')
        for words in ('<span class="tag">Not built: no domain chosen</span>', '<h2>What the builder can build today</h2>', '<h2>What someone has to write down first</h2>',
                      'A draft is a template, not knowledge: while its rule is unapproved, and no method makes the goal itself, the kernel plans nothing from it.',
                      'Not the goal itself: the kernel reads the goal from its conditions.', 'Drafted but not reviewed', 'Domain chosen by nobody: no reviewed domain shares a word with the ask.'):
            self.assertIn(words, page.replace('What this goal means is d', 'D'))
        for r in g2.catalogue():   # the table names every domain the catalogue has, by title, id and example
            self.assertIn(f'<tr><td>{r["title"]}</td><td><code>{r["id"]}</code></td><td>{r["say"]}</td></tr>', page)
        self.assertNotIn('<svg', page)
        self.assertIn('The catalogue is a reviewed pack too: the row for the new domain is an edit to that pack, reviewed like the packs it names.', page)   # a new domain is no version that only adds
        self.assertEqual([words for words, domain in g2.DEMO if domain is None and g2.build(words)['verdict'] == 'NO_DOMAIN'], ['a weekly newsletter for my donors', 'order a website'])
        tie = g2.build('order a website')   # one word of each of two domains: the stand-in does not choose
        self.assertEqual((tie['verdict'], tie['choice']['domain'], tie['choice']['tied']), ('NO_DOMAIN', None, ['order', 'website']))
        self.assertEqual(lead(tie), 'These words fit 2 reviewed domains equally (Website, Order fulfilment), so nothing was guessed. Someone has to choose one.')
        self.assertIn('To build one of them, name it: <code>--domain order</code> or <code>--domain website</code>.', tie['files']['index.html'])
        self.assertEqual(g2.build('a standing desk for the office')['verdict'], 'NO_DOMAIN')   # a word of a title is not a word of the domain
        self.assertEqual(g2.build('websites for my clients')['verdict'], 'NO_DOMAIN')          # a part of a word is not the word
        chosen = g2.build('ship the order', 'website')   # the caller may choose against the matcher; the list stays closed
        self.assertEqual((chosen['verdict'], chosen['domain']['id'], chosen['choice']['how'], chosen['plan']['goal']), ('READY', 'website', 'the caller', 'site_live'))
        self.assertIn('chosen by the caller.', chosen['files']['index.html'])
        self.assertEqual(g2.build('ship the order')['domain']['id'], 'order')
        self.assertEqual((g2.build('anything at all', 'order')['verdict'], g2.build('anything at all')['verdict']), ('WAITING', 'NO_DOMAIN'))
        self.assertEqual(([r['id'] for r in g2.catalogue()], pack(g2.CATALOGUE)['domains']), (['website', 'order', 'enquiry', 'workflow-standard'], g2.catalogue()))   # the catalogue is a pack, and it is closed

    def test_refuses_what_it_cannot_build(self):
        rows = g2.catalogue()
        two = world(['a', 'b'], methods=[m('ma', 'a'), m('mb', 'b')])
        none = world([], methods=[m('ma', 'a')])
        odd = world(['a'], methods=[m('ma', 'a', 'send_email')])
        ok = world(['a'], methods=[m('ma', 'a')])
        def no_standard(n):
            if n == 'w':
                return copy.deepcopy(ok)
            raise FileNotFoundError(n)
        one = lambda **kw: [dict(rows[0], **kw)]
        bad = {'unknown domain': lambda: g2.build('anything at all', 'a-domain-nobody-reviewed'), 'no words': lambda: g2.build(''), 'marks only': lambda: g2.build('?! \u2014 \u201c\u201d'),
               'not text': lambda: g2.build(None), 'a number': lambda: g2.build(5), 'letters that show nothing': lambda: g2.build('\u3164\u3164 \u200b'),
               'variation selectors only': lambda: g2.build('\U000e0100\U000e0101 \ufe0f'), 'mongolian selectors only': lambda: g2.build('\u180b\u180c\u180f'),
               'format characters only': lambda: g2.build('\U0001d173\U0001d17a'), 'joiners only': lambda: g2.build('\u200d\u200c'),
               'a domain that is not a name': lambda: G.build_system('ship it', rows, pack, ['order']),
               'the catalogue is not a list': lambda: G.build_system('a site', {'website': rows[0]}, pack), 'a row is not an object': lambda: G.build_system('a site', ['website'], pack),
               'two rows, one id': lambda: G.build_system('a site', rows + [rows[0]], pack), 'a row without its parts': lambda: G.build_system('a site', [{'id': 'x', 'title': 'X'}], pack),
               'blank title': lambda: G.build_system('a site', one(title='   '), pack), 'empty id': lambda: G.build_system('a site', one(id=''), pack),
               'a say that shows nothing': lambda: G.build_system('a site', one(say=' \u200b'), pack), 'empty goal': lambda: G.build_system('a site', one(goal=''), pack),
               'no words': lambda: G.build_system('a site', one(words=[]), pack), 'a blank word': lambda: G.build_system('a site', one(words=['site', ' ']), pack),
               'a blank pack': lambda: G.build_system('a site', one(packs=['  ']), pack), 'labels that are a list': lambda: G.build_system('a site', one(labels=[]), pack),
               'a label that is a number': lambda: G.build_system('a site', one(labels={'site_live': 5}), pack),
               'a string that is not text': lambda: G.build_system('a site', one(title='a\udcffb'), pack),
               'another goal than the packs leave': lambda: G.build_system('ship it', [dict(rows[1], goal='another_goal')], pack),
               'a pack that does not exist': lambda: G.build_system('ship it', [dict(rows[1], packs=['no_such_pack'])], pack),
               'a pack name that leaves the folder': lambda: G.build_system('ship it', [dict(rows[1], packs=['../scenarios/00_goal'])], g2.load_pack),
               'two standing goals': lambda: build(two), 'no standing goal': lambda: build(none), 'a kind nobody registered': lambda: build(odd),
               'a pack that is a list': lambda: G.build_system('ship it', [dict(rows[1], packs=['w'])], lambda n: []),
               'a pack that is nothing': lambda: G.build_system('ship it', [dict(rows[1], packs=['w'])], lambda n: None),
               'a pack deeper than the interpreter follows': lambda: G.build_system('ship it', [dict(rows[1], packs=['w'])], lambda n: json.loads('[' * 100000)),
               'the standard is missing': lambda: G.build_system('ship it', [{'id': 'w', 'title': 'W', 'goal': 'a', 'say': 'ship it', 'words': ['ship'], 'packs': ['w']}], no_standard)}
        for name, attempt in bad.items():
            with self.assertRaises(ValueError, msg=name):
                attempt()
        self.assertEqual(build(ok)['verdict'], 'READY')   # the same world, whole, builds

    def test_words_are_read_by_code_point(self):
        self.assertEqual(g2.build('a web\u202esite \x00for\u00a0 me\ufeff')['asked'], 'a website for me')   # what hides or reverses text is dropped, white space is one space
        s = g2.build('a website \ua7c1 for \U00016a70 us')   # letters the interpreter's own table may not know stay as they are, on every interpreter
        self.assertEqual((s['asked'], s['folder'], s['choice']['domain']), ('a website \ua7c1 for \U00016a70 us', 'a-website-for-us-' + s['files_sha256']['manifest.json'][:16], 'website'))
        self.assertEqual(G._tokens('Web-Site, WEBSITE\u2014for \u201cOrganisation\u201d \u00dcber'), {'web', 'site', 'website', 'for', 'organisation', '\u00dcber'})
        self.assertEqual((G._tokens('I am on TV at 5 pm'), G._tokens('go to the web')), (set(), {'the', 'web'}))   # a word is three characters or more
        far = g2.build('\u30a6\u30a7\u30d6\u30b5\u30a4\u30c8 \u3092 \u4f5c\u308b')   # words with no ASCII letter build too; the folder is named by the digest alone
        self.assertEqual((far['verdict'], far['folder']), ('NO_DOMAIN', 'goal-' + far['files_sha256']['manifest.json'][:16]))
        self.assertIn('<h1>\u30a6\u30a7\u30d6\u30b5\u30a4\u30c8 \u3092 \u4f5c\u308b</h1>', far['files']['index.html'])
        self.assertEqual((G._ascii_slug('../../etc/passwd'), G._ascii_slug('C:\\x ~ $(id)'), G._ascii_slug('---')), ('etc-passwd', 'c-x-id', 'goal'))
        self.assertEqual(g2.build('a site\U0001d173 \u8fba\U000e0100')['asked'], 'a site \u8fba\U000e0100')   # a format character goes; a variation selector stays with its letter

    # ---------------------------------------------------------------- C5, C6, C7: the verdict, where a plan does not get there, both answers to a question
    def test_order_words_wait_on_the_customer_and_show_both_answers(self):
        s = g2.build(ORDER)
        run = s['model_run']
        self.assertEqual((s['verdict'], s['domain']['id'], len(run['asks']), [r['status'] for r in run['path']], run['goal_held']),
                         ('WAITING', 'order', 1, ['WAITING', 'LOCAL_MODEL_EFFECTS_RECORDED'], True))
        ask = run['asks'][0]
        self.assertEqual((ask['to'], ask['asked_by'], ask['fact'], ask['question'], ask['receipt_sha256']),
                         ('customer', 'ask-customer-approval@1', 'customer_approved', 'May we send a replacement for the item that is out of stock?', run['path'][0]['receipts'][0]['sha256']))
        self.assertEqual((ask['if_yes'], [r['method'] for r in ask['if_yes']['receipts']]), (run['path'][1], ['ship-replacement@1']))
        self.assertEqual((ask['if_no']['status'], ask['if_no']['receipts'], ask['if_no']['goal_held']), ('REFUSED', [], None))
        receipts = [r for x in run['path'] for r in x['receipts']] + ask['if_no']['receipts']
        self.assertEqual([r['status'] for r in receipts], ['LOCAL_ONLY', 'LOCAL_ONLY'])
        steps = {x['method']: x for x in s['implementation']['workflow']['steps'] if x.get('method')}
        self.assertEqual((list(steps), steps['ask-customer-approval@1']['waits_for']), (['ask-customer-approval@1', 'ship-replacement@1'], 'customer'))
        page, seen = s['files']['index.html'], text(s['files']['index.html'])
        self.assertEqual(lead(s), 'Waiting on customer: one question has to be answered before the rest of the 2 steps can run.')
        for words in ('<span class="tag">Waiting on an answer</span>', '<h2>Waiting on an answer</h2>',
                      '<fieldset class="choice"><legend><b>Customer</b> is asked: May we send a replacement for the item that is out of stock?</legend>',
                      'These 2 steps, in this order, make it true that the order is complete, if customer says yes.', 'Customer is asked whether the customer has approved a replacement',
                      'Asked by the step Ask the customer. The answer must come from customer and present the receipt of this question.',
                      '<g class="ask"><title>ask-customer-approval@1 asks customer whether customer_approved</title>', '<text class="sub"', '>asks customer</text>',
                      '<g class="later"><title>ship-replacement@1 makes replacement_delivered</title>', '<text class="mark"', '>after the answer</text>',
                      'A run in the local model: with every question answered yes the plan ran through, and the goal is held',
                      'The plan executed against a model of the world, with every question answered yes.', '<p class="hint">Any one of these is enough.</p>'):
            self.assertIn(words, page)
        for words in ("The run waits. Nothing after the question has run. Looking again asks nothing and costs nothing, and a way that costs less in this domain's order of preference is still taken.",
                      'After customer said yes: the plan ran through in the local model', "The kernel's next look finds the goal held."):
            self.assertIn(words, seen)
        yes, no, end = page.index('<div class="panel y">'), page.index('<div class="panel n">'), page.index('</fieldset>')
        self.assertIn('<b>The plan runs through in the local model.</b> Ran in the local model: Ship the replacement.', page[yes:no])   # each answer shows its own outcome
        self.assertIn('<b>The run ends here: a decision stands against it, and no method may overturn that.</b></p>', page[no:end])
        self.assertEqual((page.count('class="later"'), page.count('<fieldset'), page.count('type="radio"')), (1, 1, 3))

    def test_a_yes_that_does_not_get_there_is_not_waiting(self):
        # The yes path is run to its end and the kernel is asked once more: a yes after which the kernel has no plan, or the goal does not hold, is not waiting.
        w = world(['order_done'], [('order_done', [['paid']])], [m('ask-payer', 'paid', 'ask', ASK, ask_to='payer')], [row('order_done', 'FALSE')])
        s = build(w)   # the rule's head is recorded FALSE and its last missing condition is asked: after the yes the kernel itself says the facts contradict each other
        run = s['model_run']
        self.assertEqual((s['verdict'], s['blocked_at'], [r['status'] for r in run['path']], s['standard']['status'], run['asks'][0]['if_yes']['status'], run['goal_held']),
                         ('NOT_READY', [{'reason': 'EVIDENCE_CONFLICT', 'at': ['order_done'], 'detail': None}], ['WAITING', 'EVIDENCE_CONFLICT'], 'NOT_APPLICABLE', 'EVIDENCE_CONFLICT', None))
        self.assertEqual(lead(s), 'A plan was found, but it does not get there in the local model, after payer said yes: the kernel has no plan left, because the facts contradict each other (order_done).')
        page = s['files']['index.html']
        for words in ('<span class="tag">Plan found, not ready</span>', '<div class="verdict NOT_READY">', '<h2>What stands in the way</h2>', '<h2>The questions on the way</h2>',
                      'On paper this one step makes it true that order_done. In the local model the plan does not get there; the first lines of this page say where.',
                      '<b>The run ends here: the facts contradict each other.</b>', 'A run in the local model: with every question answered yes the kernel found no plan: the facts contradict each other',
                      'with 1 question answered yes before it ended', 'Someone settling which fact is right'):
            self.assertIn(words, page)
        for words in ('Waiting on payer', 'if payer says yes', 'has the parts the standard asks for', '<h2>Waiting on an answer</h2>', 'the goal is held'):
            self.assertNotIn(words, page)
        opened = exhibit(2)   # the same with the shipped order domain and one more row (case 70): the yes ships, and the stored row then contradicts the rule
        run = opened['model_run']
        self.assertEqual((opened['verdict'], opened['blocked_at'], [r['status'] for r in run['path']], run['after']['status'], run['goal_held'], run['effects_missing']),
                         ('NOT_READY', [{'reason': 'GOAL_NOT_HELD', 'at': ['order_complete'], 'detail': 'EVIDENCE_CONFLICT'}], ['WAITING', 'LOCAL_MODEL_EFFECTS_RECORDED'], 'EVIDENCE_CONFLICT', False, []))
        self.assertEqual(lead(opened), 'A plan was found, but it does not get there in the local model, after customer said yes: every step ran, and afterwards it still does not hold that '
                                       'the order is complete (the facts contradict each other).')
        seen = text(opened['files']['index.html'])
        for words in ('Every step runs, and afterwards the goal still does not hold. Ran in the local model: Ship the replacement.', "The kernel's next look does not find the goal held.",
                      'A run in the local model: with every question answered yes every step ran, and the goal still does not hold',
                      'Every step ran in the local model, and afterwards the goal still does not hold: the facts contradict each other', 'chosen by the caller'):
            self.assertIn(words, seen)
        lone = world(['paid'], methods=[m('ask-payer', 'paid', 'ask', ASK, ask_to='payer')])
        s = with_kind('ask', lambda old: {k: v for k, v in old.items() if k != 'settle'}, lambda: build(lone))   # a run that parks on a question nobody can answer (the kind lost its books) is not waiting either
        self.assertEqual((s['verdict'], s['blocked_at'], [r['status'] for r in s['model_run']['path']], s['model_run']['asks']),
                         ('NOT_READY', [{'reason': 'STILL_WAITING', 'at': ['ask-payer'], 'detail': None}], ['WAITING'], []))
        self.assertEqual(lead(s), 'A plan was found, but it does not get there in the local model: the run still waits.')
        self.assertEqual(build(lone)['verdict'], 'WAITING')
        site = g2.catalogue()[0]   # and without any question: the website with a row that says it is not live today
        today = {'schema': 'sutra-extension/2', 'id': 'today', 'evidence': [row('site_live', 'FALSE')]}
        s = G.build_system('a website', [dict(site, packs=site['packs'] + ['today'])], lambda n: today if n == 'today' else pack(n))
        self.assertEqual((s['verdict'], [b['reason'] for b in s['blocked_at']], s['model_run']['path'][-1]['status'], s['model_run']['asks']), ('NOT_READY', ['GOAL_NOT_HELD'], 'LOCAL_MODEL_EFFECTS_RECORDED', []))
        self.assertEqual(lead(s), 'A plan was found, but it does not get there in the local model: every step ran, and afterwards it still does not hold that the website is live (the facts contradict each other).')
        self.assertNotIn('Ready:', s['files']['index.html'])
        self.assertEqual(g2.build(WEBSITE)['verdict'], 'READY')

    def test_the_first_sentence_names_the_reason_the_kernel_names(self):
        # Refuter round on the third build: after a yes the kernel had no plan left and gave two reasons. The first sentence named the first one in the order of the trace
        # (a fact that would unblock nothing: its branch is the one the yes made unnecessary), while the yes panel and the run line of the same page named the kernel's.
        s = build(world(['G'], [('G', [['c'], ['q']])], [m('ask-q', 'q', 'ask', ASK, ask_to='owner')], [row('G', 'FALSE')]))
        last = s['model_run']['path'][-1]
        self.assertEqual((s['verdict'], last['status'], last['stop_reasons'], s['blocked_at']),
                         ('NOT_READY', 'EVIDENCE_CONFLICT', ['EVIDENCE_CONFLICT', 'QUERY_EVIDENCE'],
                          [{'reason': 'QUERY_EVIDENCE', 'at': ['c'], 'detail': None}, {'reason': 'EVIDENCE_CONFLICT', 'at': ['G'], 'detail': None}]))   # the rows stay in the order of the trace
        self.assertEqual(lead(s), 'A plan was found, but it does not get there in the local model, after owner said yes: the kernel has no plan left, because the facts contradict each other (G).')
        page = s['files']['index.html']
        for words in ('<b>The run ends here: the facts contradict each other.</b>', 'A run in the local model: with every question answered yes the kernel found no plan: the facts contradict each other',
                      '<td>C <code>c</code></td><td>A needed fact is unknown and nothing may ask for it</td>', '<td>G <code>G</code></td><td>The facts contradict each other</td>'):
            self.assertIn(words, page)   # one reason on the whole page: the first sentence, the yes panel and the run line agree; the table lists both rows
        self.assertEqual(page.count('a needed fact is unknown'), 0)
        from_start = build(world(['G'], [('G', [['c'], ['q']])], [m('ask-q', 'q', 'ask', ASK, ask_to='owner')], [row('G', 'FALSE'), row('q')]))   # the same State with the answer true from the start
        self.assertEqual((from_start['verdict'], from_start['plan']['status'], lead(from_start)), ('BLOCKED', 'EVIDENCE_CONFLICT', 'Cannot start: the facts contradict each other (G).'))
        closing = exhibit(3)   # the same on shipped packs (case 71): an order that closes on the customer's word, recorded as not closed
        run = closing['model_run']
        self.assertEqual((closing['verdict'], [r['status'] for r in run['path']], run['path'][-1]['stop_reasons'], [b['reason'] for b in closing['blocked_at']], run['asks'][0]['if_no']['status'], run['after']),
                         ('NOT_READY', ['WAITING', 'EVIDENCE_CONFLICT'], ['EVIDENCE_CONFLICT', 'QUERY_EVIDENCE'], ['QUERY_EVIDENCE', 'EVIDENCE_CONFLICT'], 'REFUSED', None))
        self.assertEqual(lead(closing), 'A plan was found, but it does not get there in the local model, after customer said yes: the kernel has no plan left, because the facts contradict each other (the order is closed).')
        seen = text(closing['files']['index.html'])
        for words in ('The run ends here: the facts contradict each other.', 'The run ends here: a decision stands against it, and no method may overturn that.',
                      'After customer said yes: the facts contradict each other', 'A refund is on record refund_recorded', 'chosen by the caller'):
            self.assertIn(words, seen)
        for words in ('Waiting on customer', 'if customer says yes', 'has the parts the standard asks for'):
            self.assertNotIn(words, closing['files']['index.html'])
        # Whatever reason stands first in the order of the trace, the first sentence names the one the kernel names the run with: the refuter's fuzz found a decision, a
        # missing method and a circle named there as well as the unknown fact above.
        ask = m('ask-q', 'q', 'ask', ASK, ask_to='owner')
        firsts = {'REFUSED': world(['G'], [('G', [['d'], ['q']])], [ask], [row('G', 'FALSE'), row('d', 'FALSE', final=True)]),
                  'METHOD_ABSENT': world(['G'], [('G', [['d'], ['q']])], [ask], [row('G', 'FALSE'), row('d', 'FALSE')]),
                  'CYCLE_LIMIT': world(['G'], [('G', [['x'], ['q']])], [ask, m('mx', 'x', req=['y']), m('my', 'y', req=['x'])], [row('G', 'FALSE')])}
        for first, w in firsts.items():
            s = build(w)
            last = s['model_run']['path'][-1]
            self.assertEqual((s['verdict'], last['work_state'], last['status'], s['blocked_at'][0]['reason'], s['blocked_at'][-1]), ('NOT_READY', 'blocked', 'EVIDENCE_CONFLICT', first, {'reason': 'EVIDENCE_CONFLICT', 'at': ['G'], 'detail': None}), first)
            self.assertEqual(lead(s), 'A plan was found, but it does not get there in the local model, after owner said yes: the kernel has no plan left, because the facts contradict each other (G).', first)
            self.assertIn('<b>The run ends here: the facts contradict each other.</b>', s['files']['index.html'], first)
        # the row itself (`_headline`): the builder's own findings stay first; a look that names no row with its status (the kernel's one word for a circle and for its
        # depth limit, told apart on the page) is named by its first row; a system without rows names none
        look = lambda status, reasons: {'status': status, 'work_state': 'blocked', 'stop_reasons': reasons}
        rows = lambda *reasons: [{'reason': r, 'at': [r.lower()], 'detail': None} for r in reasons]
        system = lambda verdict, blocked, path=(), plan=None: {'verdict': verdict, 'blocked_at': blocked, 'model_run': {'path': list(path)}, 'plan': plan or look('PLAN_READY', [])}
        after_yes = [look('WAITING', []), look('EVIDENCE_CONFLICT', ['EVIDENCE_CONFLICT', 'QUERY_EVIDENCE'])]
        self.assertEqual([G._headline(x)['reason'] if G._headline(x) else None for x in (
            system('NOT_READY', rows('QUERY_EVIDENCE', 'EVIDENCE_CONFLICT'), after_yes), system('NOT_READY', rows('ROUTE_CHANGED', 'QUERY_EVIDENCE', 'EVIDENCE_CONFLICT'), after_yes),
            system('NOT_READY', rows('WORKFLOW_PROBLEM', 'QUERY_EVIDENCE', 'EVIDENCE_CONFLICT'), after_yes), system('BLOCKED', rows('METHOD_ABSENT', 'QUERY_EVIDENCE'), plan=look('QUERY_EVIDENCE', [])),
            system('BLOCKED', rows('CHAIN_TOO_DEEP'), plan=look('CYCLE_LIMIT', ['CYCLE_LIMIT'])), system('NOT_READY', rows('STEP_STOPPED'), [dict(look('STEP_STOPPED', []), work_state='stopped')]),
            system('BLOCKED', [], plan=look('METHOD_ABSENT', [])))],
            ['EVIDENCE_CONFLICT', 'ROUTE_CHANGED', 'WORKFLOW_PROBLEM', 'QUERY_EVIDENCE', 'CHAIN_TOO_DEEP', 'STEP_STOPPED', None])
        # A yes path that ends without a plan is never reported as waiting, also if the kernel's trace should name no condition for it: the builder then names the look's own status.
        keep = G._blocked_at
        G._blocked_at = lambda result, state: []
        try:
            s = build(world(['order_done'], [('order_done', [['paid']])], [m('ask-payer', 'paid', 'ask', ASK, ask_to='payer')], [row('order_done', 'FALSE')]))
        finally:
            G._blocked_at = keep
        self.assertEqual((s['verdict'], s['blocked_at'], lead(s)), ('NOT_READY', [{'reason': 'EVIDENCE_CONFLICT', 'at': [], 'detail': None}],
                                                                   'A plan was found, but it does not get there in the local model, after payer said yes: the kernel has no plan left, because the facts contradict each other.'))

    def test_another_route_than_the_plan_shown_is_not_waiting(self):
        # Refuter round one on the second build: two plans tie on cost, and after the yes the kernel plans again and takes the other one. The page, the workflow file
        # and the atoms carried steps that never ran, one of which cannot run, and the page said waiting. The steps that ran are now held to the plan that is shown.
        ask = m('ask-payer', 'paid', 'ask', ASK, ask_to='payer')
        rule = [('G', [['packed', 'paid']])]
        s = build(world(['G'], rule, [ask, m('pack-a', 'packed'), m('pack-b', 'packed', 'compile_candidate', req=['paid'], constructor='none')]))
        run = s['model_run']
        self.assertEqual((s['verdict'], s['plan']['actions'], [[x['method'] for x in r['receipts']] for r in run['path']], run['goal_held'], s['standard']['status']),
                         ('NOT_READY', ['ask-payer', 'pack-b'], [['ask-payer'], ['pack-a']], True, 'NOT_APPLICABLE'))
        self.assertEqual(s['blocked_at'], [{'reason': 'ROUTE_CHANGED', 'at': ['pack-a', 'pack-b'], 'detail': 'chosen outside the plan: pack-a; planned and not run: pack-b'}])
        self.assertEqual(lead(s), 'A plan was found, but the local model took another route, after payer said yes: the kernel chose pack-a, which is no step of the plan on this page; pack-b is a step of that plan and never ran.')
        page = s['files']['index.html']
        for words in ('<span class="tag">Plan found, not ready</span>', '<div class="verdict NOT_READY">', '>not reached</text>', 'pack-b should make it true that packed (not reached in the local model)',
                      'A run in the local model: with every question answered yes the kernel took another route than the plan on this page',
                      '<b>The kernel takes another route than the plan on this page, and afterwards the goal holds.</b> Ran in the local model: pack-a.',
                      'After payer said yes: steps that are not in the plan on this page ran in the local model',
                      'The steps that ran in the local model are not the steps of the plan on this page: chosen outside the plan: pack-a; planned and not run: pack-b',
                      'On paper these 2 steps, in this order, make it true that G.'):
            self.assertIn(words, page)
        for words in ('Waiting on payer', 'if payer says yes', 'pack-b makes it true that packed', 'the plan ran through', 'has the parts the standard asks for'):
            self.assertNotIn(words, page)
        plain = build(world(['G'], rule, [ask, m('pack-a', 'packed'), m('pack-b', 'packed', req=['paid'])]))   # the same with an ordinary step in the plan shown: it still did not run
        self.assertEqual((plain['verdict'], [b['reason'] for b in plain['blocked_at']], plain['blocked_at'][0]['at']), ('NOT_READY', ['ROUTE_CHANGED'], ['pack-a', 'pack-b']))
        stops = build(world(['G'], rule, [ask, m('pack-a', 'packed', 'compile_candidate', constructor='none'), m('pack-b', 'packed', req=['paid'])]))   # the other route stops at its first step: both are said, the route first
        self.assertEqual(([b['reason'] for b in stops['blocked_at']], [b['at'] for b in stops['blocked_at']], stops['model_run']['path'][-1]['receipts']), (['ROUTE_CHANGED', 'STEP_STOPPED'], [['pack-a'], ['pack-a']], []))
        self.assertEqual(lead(stops), 'A plan was found, but the local model took another route, after payer said yes: the kernel chose pack-a, which is no step of the plan on this page.')
        self.assertEqual(build(world(['G'], rule, [ask, m('pack-b', 'packed', req=['paid'])]))['verdict'], 'WAITING')   # one way to the condition: the plan shown is the plan that runs
        # A stated limit: the steps that ran are held to the plan as a set, not as a sequence. Two plans of the same steps tie, and after the yes the kernel runs the
        # two steps that do not depend on each other in the other order. The workflow file lists them as the first look chose them; the page's run table shows the order they ran in.
        tie = build(world(['G'], [('G', [['X', 'Y'], ['Y', 'X']])], [m('a-ask', 'Q', 'ask', ASK, ask_to='payer'), m('z', 'X', req=['Q']), m('m', 'Y')]))
        self.assertEqual((tie['verdict'], tie['plan']['actions'], [[x['method'] for x in r['receipts']] for r in tie['model_run']['path']], tie['blocked_at']),
                         ('WAITING', ['a-ask', 'z', 'm'], [['a-ask'], ['m', 'z']], []))
        self.assertIn('<td>After payer said yes: the plan ran through in the local model</td><td>m, z</td>', tie['files']['index.html'])
        for s in g2.demo():   # on every shipped system the steps that ran are steps of the plan shown, and every planned step of a path that got there ran or was skipped
            if s['verdict'] in ('READY', 'WAITING'):
                ran = [x['method'] for r in s['model_run']['path'] for x in r['receipts']] + [x for r in s['model_run']['path'] for x in r['skipped']]
                self.assertEqual(sorted(ran), sorted(s['plan']['actions']), s['asked'])

    def test_a_step_the_kernel_recorded_as_stopped_is_shown_as_a_stop(self):
        s = exhibit(1)   # the builder's components without the constructor its last step names (case 30): the kernel records the stop, the page reads it
        run = s['model_run']
        self.assertEqual((s['verdict'], s['plan']['status'], s['blocked_at'], run['path'][0]['status'], run['path'][0]['stopped'], len(run['path'][0]['receipts']), run['after']),
                         ('NOT_READY', 'PLAN_READY', [{'reason': 'STEP_STOPPED', 'at': ['construct-enquiry-candidate@1'], 'detail': 'Handler refused: No declared constructor'}], 'STEP_STOPPED',
                          {'method': 'construct-enquiry-candidate@1', 'reason': 'Handler refused: No declared constructor'}, 3, None))
        self.assertEqual(lead(s), 'A plan was found, but it stops in the local model: the step Construct the candidate cannot run (Handler refused: No declared constructor).')
        page = s['files']['index.html']
        for words in ('<g class="stop"><title>construct-enquiry-candidate@1 makes capability_candidate_created</title>', '>stops here</text>',
                      'Construct the candidate should make it true that a capability candidate is created (in the local model it could not run)',
                      'A step could not run in the local model, and the run stopped there (Construct the candidate: Handler refused: No declared constructor)',
                      'A run in the local model: a step could not run, and the run stopped there', 'On paper these 4 steps, in this order, make it true that a capability candidate is created.',
                      'A step could not run in the local model, and the run stopped there: Handler refused: No declared constructor'):
            self.assertIn(words, page)
        # a stop after a yes: the question, the yes and the stop are all on the record
        w = world(['shipped'], methods=[m('ask-ok', 'ok', 'ask', ASK, ask_to='customer'), m('cand', 'c', 'compile_candidate', constructor='none'), m('ship', 'shipped', req=['ok', 'c'])])
        s = build(w)
        ask = s['model_run']['asks'][0]
        self.assertEqual((s['verdict'], [r['status'] for r in s['model_run']['path']], ask['if_yes']['stopped'], ask['if_no']['status']),
                         ('NOT_READY', ['WAITING', 'STEP_STOPPED'], {'method': 'cand', 'reason': 'Handler refused: No declared constructor'}, 'REFUSED'))
        self.assertEqual(lead(s), 'A plan was found, but it stops in the local model, after customer said yes: the step cand cannot run (Handler refused: No declared constructor).')
        page = s['files']['index.html']
        for words in ('<b>The run stops: the step cand cannot run (Handler refused: No declared constructor).</b> Not run: cand, ship.', '>stops here</text>', '>not reached</text>',
                      'ship should make it true that shipped (not reached in the local model)', 'After customer said yes: a step could not run in the local model, and the run stopped there (cand: Handler refused: No declared constructor)'):
            self.assertIn(words, page)
        # a no after which a step stops is a stop, not the run from before the answer
        w = world(['done'], [('done', [['shipped'], ['refunded']])], [m('ask-ok', 'approved', 'ask', ASK, ask_to='customer'), m('ship', 'shipped', req=['approved']),
                                                                    m('book', 'booked', 'compile_candidate', {'compute': 5, 'money': 0, 'attention': 0}, constructor='none'),
                                                                    m('refund', 'refunded', cost={'compute': 5, 'money': 5, 'attention': 0}, req=['booked'])])
        s = build(w)
        no = s['model_run']['asks'][0]['if_no']
        self.assertEqual((s['verdict'], no['status'], no['stopped'], no['pending'], no['goal_held']), ('WAITING', 'STEP_STOPPED', {'method': 'book', 'reason': 'Handler refused: No declared constructor'}, ['book', 'refund'], None))
        page = s['files']['index.html']
        no_panel = page[page.index('<div class="panel n">'):page.index('</fieldset>')]
        self.assertIn('<b>The run stops: the step book cannot run (Handler refused: No declared constructor).</b> Not run: book, refund.', no_panel)
        self.assertNotIn('waits', no_panel)
        # the gate's own stop: a step whose prerequisite was made by a kind that stores no evidence
        spec = {'id': 'C', 'target_effect': 'x', 'components': ['cand'], 'required_effects': []}
        w = world(['shipped'], methods=[m('cand', 'c', 'compile_candidate', constructor='C'), m('ship', 'shipped', req=['c'])], constructors=[spec])
        s = build(w)
        self.assertEqual((s['verdict'], s['blocked_at']), ('NOT_READY', [{'reason': 'STEP_STOPPED', 'at': ['ship'], 'detail': 'Prerequisite not true before effect: c'}]))
        self.assertEqual(lead(s), 'A plan was found, but it stops in the local model: the step ship cannot run (Prerequisite not true before effect: c).')
        # a step that rests on a condition that holds only through a rule: on this base the kernel plans it, and the executed step stops at its gate (a stated limit of the base). The page does not call that ready.
        derived = build(world(['shipped'], [('ready', [['packed']])], [m('pack', 'packed'), m('ship', 'shipped', req=['ready'])]))
        self.assertEqual((derived['verdict'], derived['plan']['status'], derived['plan']['actions'], derived['blocked_at']),
                         ('NOT_READY', 'PLAN_READY', ['pack', 'ship'], [{'reason': 'STEP_STOPPED', 'at': ['ship'], 'detail': 'Prerequisite not true before effect: ready'}]))
        # a handler that fails is the kernel's recorded stop as well: the builder reads the result, it catches no error of a step
        def fails(state, mm, mid, deps):
            raise OSError('disk')
        s = with_kind('simulate_fact', lambda old: dict(old, run=fails), lambda: g2.build(WEBSITE))
        self.assertEqual((s['verdict'], s['blocked_at'], s['model_run']['path'][0]['receipts']), ('NOT_READY', [{'reason': 'STEP_STOPPED', 'at': ['plan-site@1'], 'detail': 'Handler failed: OSError'}], []))
        source = Path(G.__file__).read_text(encoding='utf-8')
        self.assertEqual(re.findall(r'\bRuntimeError\b|\bStop\b', source), [])   # the builder names no error of a step: it reads the kernel's record
        self.assertEqual(g2.build(WEBSITE)['verdict'], 'READY')

    def test_an_effect_that_does_not_hold_is_not_ready(self):
        goal = pack('30_build_goal')['goals'][0]   # the lab's own constructor packs (case 15): the last step runs and stores no evidence of its effect
        s = G.build_system('build it', [{'id': 'build', 'title': 'Builder', 'goal': goal, 'say': 'build it', 'words': ['build'], 'packs': ['30_build_goal', '31_build_theory', '32_builder_components']}], pack)
        self.assertEqual((s['verdict'], s['plan']['status'], s['blocked_at'], s['model_run']['effects_missing'], s['model_run']['path'][0]['status']),
                         ('NOT_READY', 'PLAN_READY', [{'reason': 'EFFECT_NOT_MADE', 'at': ['construct-enquiry-candidate@1'], 'detail': None},
                                                      {'reason': 'GOAL_NOT_HELD', 'at': [goal], 'detail': 'PLAN_READY'}], ['construct-enquiry-candidate@1'], 'LOCAL_MODEL_EFFECTS_RECORDED'))
        self.assertEqual(lead(s), 'A plan was found, but it does not get there in the local model: the step construct-enquiry-candidate@1 ran, and what it should make true does not hold afterwards.')
        page = s['files']['index.html']
        for words in ('>effect not made</text>', 'construct-enquiry-candidate@1 should make it true that capability_candidate_created (in the local model it did not)',
                      'Every step ran in the local model, and afterwards the goal still does not hold: the kernel would plan the same steps again', 'A method whose step stores its effect as evidence',
                      'A run in the local model: every step ran, and the goal still does not hold'):
            self.assertIn(words, page)

    def _asks(self, n, extra=()):
        return world(['done'], methods=[m(f'ask-{i}', f'ok{i}', 'ask', ASK, ask_to=f'party{i}', question=f'May step {i} go ahead?') for i in range(n)] + list(extra)
                     + [m('ship', 'done', req=[f'ok{i}' for i in range(n)] + [x['effect'] for x in extra])], budget={'attention': 9})

    def test_the_yes_path_is_followed_to_its_end(self):
        two = build(self._asks(2))
        run, page = two['model_run'], two['files']['index.html']
        self.assertEqual((two['verdict'], [a['to'] for a in run['asks']], [r['status'] for r in run['path']], run['goal_held']),
                         ('WAITING', ['party0', 'party1'], ['WAITING', 'WAITING', 'LOCAL_MODEL_EFFECTS_RECORDED'], True))
        self.assertEqual(lead(two), 'Waiting on party0, party1: 2 questions have to be answered, one after the other, before the plan is through.')
        for words in ('These 3 steps, in this order, make it true that done, if every question on the way is answered yes.',
                      '<legend><b>Party1</b> is asked: May step 1 go ahead?</legend>', 'Asked by the step ask-1, only after party0 said yes. The answer must come from party1',
                      '<b>The run goes on and waits again: the next question goes to party1.</b> Ran in the local model: ask-1. Not run: ship.',
                      '<g class="ask later"><title>ask-1 asks party1 whether ok1</title>', '>asked after the answer</text>', '>after the answer</text>'):
            self.assertIn(words, page)
        self.assertEqual((page.count('<fieldset class="choice">'), page.count('>asked after the answer</text>'), page.count('>after the answer</text>')), (2, 1, 1))
        six = build(self._asks(6))   # more questions than the page shows panels for: every one is asked, counted and named
        page = six['files']['index.html']
        self.assertEqual((six['verdict'], len(six['model_run']['asks']), six['model_run']['path'][-1]['status'], page.count('<fieldset class="choice">')), ('WAITING', 6, 'LOCAL_MODEL_EFFECTS_RECORDED', 4))
        self.assertEqual(lead(six), 'Waiting on party0, party1, party2, party3, party4, party5: 6 questions have to be answered, one after the other, before the plan is through.')
        for words in ('The plan asks 6 questions. The first 4 are shown above with both answers; these follow, each only after every question before it was answered yes:',
                      '<li><b>Party4</b> is asked: May step 4 go ahead?</li><li><b>Party5</b> is asked: May step 5 go ahead?</li>'):
            self.assertIn(words, page)
        self.assertNotIn('at least', page)
        # five questions and then a step that cannot run: every answer is given before the verdict is
        five = build(self._asks(5, [m('cand', 'c', 'compile_candidate', constructor='none')]))
        self.assertEqual((five['verdict'], [r['status'] for r in five['model_run']['path']], five['blocked_at'][0]['reason']), ('NOT_READY', ['WAITING'] * 5 + ['STEP_STOPPED'], 'STEP_STOPPED'))
        self.assertEqual(lead(five), 'A plan was found, but it stops in the local model, after party0, party1, party2, party3, party4 said yes: the step cand cannot run (Handler refused: No declared constructor).')
        last = world(['done'], [('done', [['a', 'ok']])], [m('mk-a', 'a'), m('ask-ok', 'ok', 'ask', ASK, ask_to='owner', req=['a'])])   # the question is the last step
        s = build(last)
        self.assertEqual((s['verdict'], [r['status'] for r in s['model_run']['path']]), ('WAITING', ['WAITING', 'SUPPORTED_BY_EVIDENCE']))
        self.assertEqual(lead(s), 'Waiting on owner: one question has to be answered and nothing else is left to run.')
        self.assertIn('<b>With this answer the goal holds; no step is left to run.</b>', s['files']['index.html'])

    def test_a_no_shows_what_the_kernel_did(self):
        routes = [('done', [['shipped'], ['refunded']])]
        w = world(['done'], routes, [m('ask-ok', 'approved', 'ask', ASK, ask_to='customer'), m('ship', 'shipped', req=['approved']), m('refund', 'refunded', cost={'compute': 5, 'money': 5, 'attention': 0})])
        s = build(w)   # a no that takes another route that runs
        no = s['model_run']['asks'][0]['if_no']
        self.assertEqual((s['verdict'], no['status'], [r['method'] for r in no['receipts']], no['goal_held']), ('WAITING', 'LOCAL_MODEL_EFFECTS_RECORDED', ['refund'], True))
        self.assertIn('<b>Another route is taken and gets there.</b> Ran in the local model: refund.', s['files']['index.html'])
        w = world(['done'], routes, [m('ask-ok', 'approved', 'ask', ASK, ask_to='customer'), m('ship', 'shipped', req=['approved']), m('ask-boss', 'boss_ok', 'ask', ASK, ask_to='boss'),
                                     m('refund', 'refunded', cost={'compute': 5, 'money': 5, 'attention': 0}, req=['boss_ok'])])
        s = build(w)   # a no after which the other route asks someone else: the no path is not followed further, and the page says where it stands
        no = s['model_run']['asks'][0]['if_no']
        self.assertEqual((s['verdict'], len(s['model_run']['asks']), no['status'], no['goal_held']), ('WAITING', 1, 'WAITING', None))
        self.assertIn('<b>Another route is taken and waits again: the next question goes to boss.</b> Ran in the local model: ask-boss. Not run: refund.', s['files']['index.html'])
        w = world(['done'], routes, [m('ask-ok', 'approved', 'ask', ASK, ask_to='customer'), m('ship', 'shipped', req=['approved']), m('refund', 'refunded', cost={'compute': 5, 'money': 5, 'attention': 0})],
                  [row('refunded', 'FALSE'), row('done', 'FALSE')])
        s = build(w)   # a no whose other route runs and still does not reach the goal
        self.assertEqual((s['verdict'], s['model_run']['asks'][0]['if_no']['goal_held']), ('NOT_READY', False))
        self.assertIn('<b>Another route is taken, and afterwards the goal still does not hold.</b>', s['files']['index.html'])
        rec = json.loads(g2.build(ORDER)['files']['record.json'])   # the kernel's own chain says which answer closed the question on each path
        closed = lambda r: [(e['data']['truth'], e['data']['source']) for e in r['trace'] if e['operation'] == 'ASK_CLOSED']
        self.assertEqual((closed(rec['runs'][1]), closed(rec['no_runs'][0])), ([('TRUE', 'STAMP:customer')], [('FALSE', 'STAMP:customer')]))

    def test_blocked_goal_says_where_and_why(self):
        labels = g2.catalogue()[1]['labels']
        bare = {'id': 'bare', 'title': 'Bare order', 'goal': 'order_complete', 'say': 'ship it', 'words': ['ship'], 'packs': ['00_goal', '01_domain', '02_methods', '04_admission'], 'labels': labels}
        s = G.build_system('ship it', [bare], pack)
        self.assertEqual((s['verdict'], s['plan']['status'], s['model_run']['path'], s['standard']['status']), ('BLOCKED', 'QUERY_EVIDENCE', [], 'NOT_APPLICABLE'))
        self.assertEqual(s['blocked_at'], [{'reason': 'METHOD_ABSENT', 'at': ['original_stock'], 'detail': None}, {'reason': 'QUERY_EVIDENCE', 'at': ['customer_approved'], 'detail': None}])
        self.assertEqual(lead(s), 'Cannot start: a needed fact is unknown and nothing may ask for it (the customer has approved a replacement).')   # the reason and the place are one row of the kernel's trace
        page = s['files']['index.html']
        for words in ('<span class="tag">No plan yet</span>', '<h2>Why it cannot start</h2>', '<summary>Why there is no picture</summary>', 'No plan can yet make it true that the order is complete.',
                      'Who may do what: no step is planned', '<td>The original item is in stock <code>original_stock</code></td><td>No reviewed way exists to make a needed condition true</td><td>A reviewed method that makes this condition true</td>',
                      'The workflow, step by step: no method step,'):
            self.assertIn(words, page)
        for words in ('<svg', 'A run in the local model', 'has the parts the standard asks for', 'Why this picture', 'Nothing needs doing'):
            self.assertNotIn(words, page)
        revoked = G.build_system('ship it', [dict(bare, packs=['00_goal', '01_domain', '02_methods', '03_approval', '04_admission', '13_revoke_authority'])], pack)
        self.assertEqual((revoked['verdict'], revoked['plan']['status']), ('BLOCKED', 'AUTHORITY_REQUIRED'))
        self.assertIn({'reason': 'AUTHORITY_REQUIRED', 'at': ['ship-replacement@1'], 'detail': None}, revoked['blocked_at'])
        self.assertEqual(lead(revoked), 'Cannot start: a step has no permission to run (Ship the replacement).')
        both = [('done', [['a', 'b']])]
        names = {'mk-a': 'Make A', 'mk-b': 'Make B'}
        slot = build(world(['done'], both, [m('mk-a', 'a'), m('mk-b', 'b')], providers={'prov': 1}), labels=names)   # two steps, one free slot: the row names both, each by its label
        self.assertEqual((slot['blocked_at'], lead(slot)), ([{'reason': 'PROVIDER_REQUIRED', 'at': ['mk-a', 'mk-b'], 'detail': None}], 'Cannot start: nobody is free to do a step (Make A, Make B).'))
        self.assertIn('<td>Make A, Make B <code>mk-a, mk-b</code></td>', slot['files']['index.html'])
        short = build(world(['done'], both, [m('mk-a', 'a'), m('mk-b', 'b', provider='other')], providers={'prov': 3, 'other': 0}), labels=names)   # two providers, one without a free slot: the row names its step only
        self.assertEqual((short['blocked_at'], lead(short)), ([{'reason': 'PROVIDER_REQUIRED', 'at': ['mk-b'], 'detail': None}], 'Cannot start: nobody is free to do a step (Make B).'))
        grant = build(world(['done'], both, [m('mk-a', 'a'), m('mk-b', 'b', grant='other')]), labels=names)   # two steps, one without its grant: the row names that one only
        self.assertEqual((grant['blocked_at'], lead(grant)), ([{'reason': 'AUTHORITY_REQUIRED', 'at': ['mk-b'], 'detail': None}], 'Cannot start: a step has no permission to run (Make B).'))
        dear = build(world(['done'], both, [m('mk-a', 'a', cost={'compute': 8, 'money': 0, 'attention': 0}), m('mk-b', 'b', cost={'compute': 8, 'money': 0, 'attention': 0})]))
        self.assertEqual(lead(dear), 'Cannot start: the budget does not cover the plan (mk-a, mk-b; compute: needs 16, has 10).')
        chain = lambda n: world(['p0'], methods=[m(f's{i}', f'p{i}', cost={'compute': 0}, req=[f'p{i + 1}']) for i in range(n - 1)] + [m(f's{n - 1}', f'p{n - 1}', cost={'compute': 0})])
        deep = build(chain(21))   # the kernel logs one word for a circle and for its depth limit: the page tells them apart
        self.assertEqual((deep['plan']['status'], deep['blocked_at'], lead(deep)),
                         ('CYCLE_LIMIT', [{'reason': 'CHAIN_TOO_DEEP', 'at': ['p20'], 'detail': '20 levels'}], 'Cannot start: the chain of conditions is deeper than the kernel follows (p20; 20 levels).'))
        self.assertIn('A shorter chain of conditions', deep['files']['index.html'])
        self.assertEqual(lead(build(chain(20))), 'Ready: 20 steps in order, and nothing waits on anyone.')
        circle = build(world(['a'], methods=[m('ma', 'a', req=['b']), m('mb', 'b', req=['a'])]))
        self.assertEqual((circle['blocked_at'][0]['reason'], lead(circle)), ('CYCLE_LIMIT', 'Cannot start: the conditions depend on each other in a circle (a).'))
        policy = build(world(['done'], methods=[m('ship', 'done', req=['export_ok'])], evidence=[row('export_ok', 'FALSE', final=True, source='policy/export-control')]))
        self.assertEqual(lead(policy), 'Cannot start: a decision stands against it, and no method may overturn that (export_ok).')
        nothing = build(world(['done']))
        self.assertEqual((nothing['verdict'], lead(nothing)), ('BLOCKED', 'Cannot start: nobody has written down what this goal means (done).'))
        unnamed = build(world(['G'], methods=[m('mk', 'G', req=[''])]))   # a condition whose name is the empty string is the kernel's row all the same (refuter round one, a note)
        self.assertEqual((unnamed['verdict'], unnamed['blocked_at'], lead(unnamed)),
                         ('BLOCKED', [{'reason': 'QUERY_EVIDENCE', 'at': [''], 'detail': None}], 'Cannot start: a needed fact is unknown and nothing may ask for it (a name that shows nothing).'))
        self.assertNotIn('The kernel recorded no specific condition.', unnamed['files']['index.html'])

    def test_ready_needs_a_well_formed_workflow_that_meets_the_standard(self):
        keep = G.validate_workflow   # the generator gives no ready plan a malformed workflow, so the check is shown to bite with a validator that finds a problem
        G.validate_workflow = lambda wf: ['step x comes before its prerequisite y']
        try:
            s = g2.build(WEBSITE)
        finally:
            G.validate_workflow = keep
        self.assertEqual((s['verdict'], s['blocked_at'], s['workflow_problems'], s['standard']['status']),
                         ('NOT_READY', [{'reason': 'WORKFLOW_PROBLEM', 'at': ['step x comes before its prerequisite y'], 'detail': None}], ['step x comes before its prerequisite y'], 'NOT_APPLICABLE'))
        self.assertEqual(lead(s), 'A plan was found, but the workflow generated from it is not well formed: step x comes before its prerequisite y.')
        keep = G.workflow_facts   # and the same for the standard: a checklist that finds a part missing
        G.workflow_facts = lambda wf: [dict(r, truth='FALSE') if r['predicate'] == 'has_trigger' else r for r in keep(wf)]
        try:
            s = g2.build(WEBSITE)
        finally:
            G.workflow_facts = keep
        self.assertEqual((s['verdict'], s['blocked_at'], s['standard']['registrable']), ('NOT_READY', [{'reason': 'STANDARD_NOT_MET', 'at': ['has_trigger'], 'detail': 'METHOD_ABSENT'}], False))
        self.assertEqual(lead(s), 'A plan was found, but the workflow generated from it lacks a part the standard asks for: has_trigger.')
        self.assertIn('has the parts the standard asks for: no, 2 of 3', s['files']['index.html'])
        a = g2.build(WEBSITE)
        wf = a['implementation']['workflow']   # the standard's verdict is the kernel's: one step without a check fails it
        broken = copy.deepcopy(wf)
        del broken['steps'][2]['verify']
        standard, kinds = [pack(n) for n in G.STANDARD], {k: dict(ACTIONS[k]) for k in G.KINDS}
        self.assertEqual([(G._standard(x, standard, kinds)[0]['registrable'], G._standard(x, standard, kinds)[0]['status']) for x in (wf, broken)], [(True, 'SUPPORTED_BY_EVIDENCE'), (False, 'METHOD_ABSENT')])
        self.assertEqual(G._standard(wf, standard, kinds)[0]['rule'], 'R-REGISTRABLE@1')
        judged = json.loads(a['files']['record.json'])['standard']   # the judgement ran on the standard's two packs, and kept exactly the checklist of this very workflow
        self.assertEqual([p['pack'] for p in judged['provenance']], list(G.STANDARD))
        self.assertEqual([e['data'] for e in judged['trace'] if e['operation'] == 'RETAIN'],
                         [{'predicate': c, 'source': 'adapter:standards/workflow@1', 'version': 'wf-' + digest(wf)[:12]} for c in ('has_trigger', 'every_step_has_check', 'has_overall_verify')])
        twins = build(world(['done'], methods=[m('make a', 'a'), m('make-a', 'done', req=['a'])]))   # two method names that give one slug: on this base the generator numbers the second, and the page shows two steps
        ids = [x['id'] for x in twins['implementation']['workflow']['steps'] if x.get('method')]
        self.assertEqual((twins['verdict'], ids, twins['workflow_problems'], len(picture(twins['files']['index.html'])[0])), ('READY', ['make-a', 'make-a-2'], [], 2))

    # ---------------------------------------------------------------- C8: the page
    EVIL = '"><img src=x onerror=alert(1)><script>x</script>\'&\u202e\x1b[31m\x00'

    def _hostile(self, **more):
        E = self.EVIL
        asks = [m(f'ask{i}' + E, f'ok{i}' + E, 'ask', ASK, ask_to=f'party{i}' + E, question=f'q{i}' + E, grant='g' + E, provider='prov' + E) for i in range(2)]
        return dict({'schema': 'sutra-extension/2', 'id': 'w' + E, 'scope': 'org' + E, 'goals': ['done' + E],
                     'rules': [{'id': 'R' + E, 'head': 'done' + E, 'branches': [['made' + E], ['other' + E]], 'approved': True, 'source': 'src' + E}],
                     'methods': [m('prep' + E, 'ready' + E, grant='g' + E, provider='prov' + E, req=['given' + E])] + asks
                                + [m('make' + E, 'made' + E, grant='g' + E, provider='prov' + E, req=['ready' + E, 'ok0' + E, 'ok1' + E])],
                     'evidence': [row('given' + E, source='src' + E, version='v' + E)], 'providers': {'prov' + E: 9}, 'grants': ['g' + E]}, **more)

    def test_page_escapes_every_string_it_was_given(self):
        E = self.EVIL
        for words in ('<script>alert(1)</script> website', '"><img src=x onerror=alert(1)> newsletter', "'; drop table goals; -- site"):
            page = g2.build(words)['files']['index.html']
            self.assertNotIn('<script', page.lower())
            self.assertNotIn('<img', page.lower())
        self.assertIn('<h1>&lt;script&gt;alert(1)&lt;/script&gt; website</h1>', g2.build('<script>alert(1)</script> website')['files']['index.html'])
        w = self._hostile()
        names = ['done', 'made', 'other', 'ready', 'given', 'ok0', 'ok1', 'prep', 'ask0', 'ask1', 'make']
        entry = lambda **kw: dict({'id': 'w' + E, 'title': 'T' + E, 'goal': 'done' + E, 'say': 'say' + E, 'words': ['ship'], 'packs': ['w']}, **kw)
        load = lambda world_: (lambda n: copy.deepcopy(world_) if n == 'w' else pack(n))
        blocked, conflict = self._hostile(grants=[]), self._hostile()
        conflict['evidence'] = conflict['evidence'] + [row('done' + E, 'FALSE', source='src' + E)]
        stopped = self._hostile()
        stopped['methods'][0] = m('prep' + E, 'ready' + E, 'compile_candidate', grant='g' + E, provider='prov' + E, req=['given' + E], constructor='none' + E)
        pages = {'waiting, raw names': G.build_system('ship it', [entry()], load(w)),
                 'waiting, labels': G.build_system('ship it', [entry(labels={n + E: 'L' + n + E for n in names})], load(w)),
                 'no plan': G.build_system('ship it', [entry()], load(blocked)), 'a yes that does not get there': G.build_system('ship it', [entry()], load(conflict)),
                 'a stop': G.build_system('ship it', [entry()], load(stopped)), 'no domain': G.build_system('zzz' + E, [entry()], load(w)),
                 'a tie': G.build_system('ship it', [entry(), entry(id='v' + E)], load(w))}
        self.assertEqual([s['verdict'] for s in pages.values()], ['WAITING', 'WAITING', 'BLOCKED', 'NOT_READY', 'NOT_READY', 'NO_DOMAIN', 'NO_DOMAIN'])
        for name, s in pages.items():
            page = s['files']['index.html']
            seen = tags(page)
            self.assertEqual(seen.names - ALLOWED, set(), name)
            self.assertEqual({k for _, k, _ in seen.attrs} - ATTRS, set(), name)
            self.assertEqual([a for a in seen.attrs if a[0] == 'input' and a[1] == 'type' and a[2] != 'radio'], [], name)
            self.assertEqual(sorted(set(seen.hrefs)), sorted(n for n in s['file_names'] if n != 'index.html'), name)   # every link is a file of the system, by its fixed name
            self.assertTrue(set(s['files']) in (set(G.BUILT_FILES), set(G.DRAFT_FILES)) and all(ch.isascii() and (ch.isalnum() or ch == '-') for ch in s['folder']), name)
            for raw in ('<img', '<script', 'onerror=alert(1)>', '\u202e', '\x1b', '\x00', "'&"):   # the markup arrives as text, and what hides or reverses text does not arrive
                self.assertNotIn(raw, page, name)
            self.assertIn('&lt;script&gt;x&lt;/script&gt;', page, name)
            strict = check_module()['markup_of'](page.replace(G.CSS, '', 1))   # the independent checks read a page strictly (tags and text, nothing else): every page the builder writes is one they take
            self.assertTrue(strict is not None and strict[0] <= check_module()['TAGS'] and {k for _, k, _ in strict[1]} <= check_module()['ATTRS'], name)
        self.assertEqual(pages['waiting, raw names']['model_run']['path'][0]['pending'], ['ask1' + E, 'make' + E])   # the answer panels of this page name steps not yet run
        hidden = build(world(['G\u3164'], methods=[m('mk', 'G\u3164')]))   # a name with a letter that shows nothing: the page links the file that was written (refuter round one, a note)
        self.assertEqual((sorted(hidden['files']), sorted(set(tags(hidden['files']['index.html']).hrefs))), (sorted(G.BUILT_FILES), sorted(n for n in G.BUILT_FILES if n != 'index.html')))

    def test_picture_has_a_box_per_step_and_arrows_that_cross_no_box(self):
        fan = world(['done'], [('done', [['e1', 'e2', 'e3']])], [m('first', 'a'), m('second', 'b', req=['a']), m('third', 'c', req=['b']), m('x1', 'e1', req=['a', 'c']),
                                                                  m('x2', 'e2', req=['a', 'b', 'c']), m('x3', 'e3', req=['a'])])
        licence = world(['site_live'], methods=[m('write-content', 'content_written'), m('build-pages', 'pages_built', req=['content_written']), m('get-licence', 'licence_held'),
                                                m('publish', 'site_live', req=['pages_built', 'licence_held'])])   # an arrow that would run through the box of an unrelated step goes round it
        for name, s in (('website', g2.build(WEBSITE)), ('order', g2.build(ORDER)), ('fan', build(fan)), ('licence', build(licence)), ('six questions', build(self._asks(6)))):
            page, wf = s['files']['index.html'], s['implementation']['workflow']
            rects, paths, heads = picture(page)
            self.assertEqual((len(rects), len(paths), len(heads)), (len([x for x in wf['steps'] if x.get('method')]), len(wf['edges']), len(wf['edges'])), name)
            self.assertEqual(len(set(rects)), len(rects), name)   # no two steps share a box
            self.assertTrue(all(pts[0][0] < head[0] for pts, head in zip(paths, heads)), name)   # every arrow points forward
            self.assertEqual(crossings(page), [], name)
            box = re.search(r'<svg class="plan" viewBox="0 0 (\d+) (\d+)" width="(\d+)" height="(\d+)"', page).groups()
            self.assertEqual(box[:2], box[2:], name)   # drawn at its own size: a wide plan scrolls, it is not shrunk until the text cannot be read
            self.assertNotIn('style=', page, name)
        self.assertNotIn('max-width:100%', G.CSS)
        self.assertEqual(len(picture(build(licence)['files']['index.html'])[1][2]), 5)   # the arrow that skips a column goes round: five points, not a straight line
        self.assertLessEqual(int(re.search(r'viewBox="0 0 (\d+)', g2.build(WEBSITE)['files']['index.html']).group(1)), 818)   # four steps in a row fit the page
        long = build(world(['done'], methods=[m('mk', 'done')]), labels={'mk': 'Write every single page of the new website and check each of them twice', 'done': 'the whole of the website is written, checked and ready for the people who asked'})
        page = long['files']['index.html']   # long names are wrapped on two lines and cut with three dots, not run out of their box
        self.assertEqual(re.findall(r'<text[^>]*>([^<]*)</text>', page), ['Write every single page', 'of the new website...', 'the whole of the website is', 'written, checked and...'])

    def test_sentences_fit_the_state(self):
        one = build(world(['done'], methods=[m('mk', 'done')]))
        self.assertEqual(lead(one), 'Ready: one step, and nothing waits on anyone.')
        for words in ('This one step makes it true that done.', 'Who may do what: one step has its grant', 'The workflow, step by step: one method step,'):
            self.assertIn(words, one['files']['index.html'])
        true = build(world(['done'], methods=[m('mk', 'done')], evidence=[row('done')]))   # nothing to do: no picture, no step count, no run of steps
        page = true['files']['index.html']
        self.assertEqual((true['verdict'], lead(true), true['model_run']['path'][0]['status']), ('READY', 'Already true: the facts support the goal and no step is needed.', 'SUPPORTED_BY_EVIDENCE'))
        for words in ('<p>No step is needed or possible right now.</p>', '<summary>Why there is no picture</summary>', 'Nothing needs doing: the facts already support that done.',
                      'A run in the local model: nothing had to run: the facts already support the goal', 'Who may do what: no step is planned'):
            self.assertIn(words, page)
        for words in ('<svg', 'These 0 steps', 'Why this picture'):
            self.assertNotIn(words, page)
        w = world(['shipped'], methods=[m('prepare-quote', 'quote'), m('ask-approval', 'approved', 'ask', ASK, req=['quote'], ask_to='customer'), m('ship', 'shipped', req=['quote', 'approved'])],
                  evidence=[row('approved', depends_on=[{'predicate': 'quote', 'version': 'local-sim-1'}])])
        s = build(w)   # a planned question that is already answered when its turn comes: the page does not say someone is asked
        page = s['files']['index.html']
        self.assertEqual((s['verdict'], s['model_run']['path'][0]['skipped'], lead(s)),
                         ('READY', ['ask-approval'], 'Ready: 3 steps in order, and nothing waits on anyone. One of them is already true at its turn and is skipped.'))
        for words in ('<g class="ask skipped">', '>already true: skipped</text>', 'customer is not asked, because it is already true that approved', '<td>prepare-quote, ship</td><td>ask-approval</td>'):
            self.assertIn(words, page)
        twins = build(world(['done'], [('done', [['y', 'z']])], [m('u1', 'u', cost={'compute': 0}), m('u2', 'u', cost={'compute': 0}), m('y', 'y', req=['u']), m('z', 'z', req=['u'])]))
        self.assertEqual((twins['verdict'], twins['workflow_problems'], twins['model_run']['path'][0]['skipped']), ('READY', [], ['u2']))   # two methods for one fact in one plan: the second is skipped, and the page says so
        self.assertIn('u2 is skipped, because it is already true that u', twins['files']['index.html'])
        style = None
        for s in g2.demo():   # nothing on any page is loaded from outside, every page says what it is, and all carry one style sheet and their own words as the title
            page = s['files']['index.html']
            for words in ('http', '@import', 'url(', 'src=', '<script', '<link', '<form', '<iframe'):
                self.assertNotIn(words, page.lower(), s['asked'])
            for words in ('<span class="tag">Proposal only</span>', f'<span class="tag">{G.VERDICT_WORDS[s["verdict"]]}</span>', f'<div class="verdict {s["verdict"]}">',
                          'nothing on this page has run outside a local model, and running a step for real is outside this lab', f'<code>{s["system_sha256"]}</code>',
                          f'<title>{G._short(s["asked"], 60)}</title><style>{G.CSS}</style></head><body><main>'):
                self.assertIn(words, page, s['asked'])
            self.assertEqual((sorted(set(tags(page).hrefs)), page.count('<style')), (sorted(n for n in s['file_names'] if n != 'index.html'), 1), s['asked'])
            style = style or re.search(r'<style>(.*?)</style>', page, re.S).group(1)
        self.assertEqual(hashlib.sha256(style.encode('utf-8')).hexdigest(), check_module()['STYLE_SHA256'])   # the digest the independent checks hold every page's style sheet to
        long = g2.build('a website ' + 'for the people of the town ' * 4)
        self.assertIn(f'<title>{long["asked"][:57]}...</title>', long['files']['index.html'])   # the title is the words, cut to sixty characters

    def test_what_a_mutation_run_changed_on_a_page_unseen_is_held(self):
        # Refuter round on the third build (refuter 2, finding 5): single mutations of the builder that change what a page or a folder says, and no unit test failed.
        dep = lambda p: [{'predicate': p, 'version': 'local-sim-1'}]
        two = build(world(['shipped'], methods=[m('prep', 'quote'), m('ask-a', 'a_ok', 'ask', ASK, req=['quote'], ask_to='customer'), m('ask-b', 'b_ok', 'ask', ASK, req=['quote'], ask_to='bank'),
                                                m('ship', 'shipped', req=['quote', 'a_ok', 'b_ok'])], evidence=[row('a_ok', depends_on=dep('quote')), row('b_ok', depends_on=dep('quote'))]))
        self.assertEqual((two['verdict'], two['model_run']['path'][0]['skipped'], lead(two)),   # two planned steps already true at their turn: the first sentence counts them
                         ('READY', ['ask-a', 'ask-b'], 'Ready: 4 steps in order, and nothing waits on anyone. 2 of them are already true at their turn and are skipped.'))
        later = build(world(['done'], [('done', [['y', 'z']])], [m('ask', 'approved', 'ask', ASK, ask_to='customer'), m('u1', 'u', cost={'compute': 0}, req=['approved']),
                                                              m('u2', 'u', cost={'compute': 0}, req=['approved']), m('y', 'y', req=['u']), m('z', 'z', req=['u'])]))
        self.assertEqual((later['verdict'], [r['skipped'] for r in later['model_run']['path']]), ('WAITING', [[], ['u2']]))   # after the answer a step is already true at its turn: the yes panel says so
        self.assertIn('<div class="panel y"><p><b>The plan runs through in the local model.</b> Ran in the local model: u1, y, z. Already true at their turn and skipped: u2.</p></div>',
                      later['files']['index.html'])
        news = g2.build('a weekly newsletter for my donors')   # the six lines someone has to write down first, each on the page
        listed = re.findall(r'<li>([^<]*)</li>', news['files']['index.html'].split('<h2>What someone has to write down first</h2><ol>')[1].split('</ol>')[0])
        self.assertEqual((len(G.TO_WRITE), news['draft']['to_write'], listed), (6, G.TO_WRITE, G.TO_WRITE))
        named = build(world(['done'], methods=[m('ask', 'approved', 'ask', ASK, ask_to='émile'), m('mk', 'done', req=['approved'])]), labels={'mk': 'écrire le site'})
        page = named['files']['index.html']   # a name that begins outside ASCII is written as it was given: no Unicode table of the interpreter makes a capital of it
        for words in ('<legend><b>émile</b> is asked:', '<td>écrire le site <code>mk</code></td>'):
            self.assertIn(words, page)
        self.assertEqual((G._cap('émile'), G._cap('emile')), ('émile', 'Emile'))
        self.assertEqual((G._ascii_slug('x' * 39 + ' yes'), G._ascii_slug(ORDER)), ('x' * 39, 'complete-a-customer-order-when-the-item'))   # cut at forty characters, and never ending in a dash
        self.assertTrue(g2.build(ORDER)['folder'].startswith('complete-a-customer-order-when-the-item-') and '--' not in g2.build(ORDER)['folder'])
        tall = build(world(['done'], methods=[m('ask', 'approved', 'ask', ASK, ask_to='customer'), m('mk', 'done', req=['approved'])]),
                     labels={'mk': 'Write every single page of the new website', 'done': 'the whole of the website is written and checked'})
        boxes = re.findall(r'<rect x="\d+" y="(\d+)" width="\d+" height="(\d+)" rx="8"/>((?:<text[^>]*>[^<]*</text>)+)</g>', tall['files']['index.html'])
        self.assertEqual(max(len(re.findall('<text', t)) for _, _, t in boxes), 5)   # two lines of name, two of what it makes, one mark: a box of five lines holds all five
        self.assertTrue(all(max(int(y) for y in re.findall(r' y="(\d+)"', t)) + 4 <= int(top) + int(high) for top, high, t in boxes))
        twice = build(world(['G'], [('G', [['c', 'a'], ['c', 'b']])], [m('ma', 'a'), m('mb', 'b')]))   # the kernel's trace names the unknown c once for each branch: the page names it once
        plan = json.loads(twice['files']['record.json'])['plan']
        self.assertEqual(([e['data']['predicate'] for e in plan['trace'] if e['operation'] == 'QUERY_EVIDENCE'], twice['blocked_at']), (['c', 'c'], [{'reason': 'QUERY_EVIDENCE', 'at': ['c'], 'detail': None}]))
        self.assertEqual(twice['files']['index.html'].count('<code>c</code>'), 1)
        nothing = build(world(['done']))   # a look without a plan whose trace names no condition is not reached with packs: the page says so all the same, for a system changed by hand
        page = G._page(dict(nothing, blocked_at=[]), json.loads(nothing['files']['record.json']))
        for words in ('<p class="lead">Cannot start: nobody has written down what this goal means.</p>', '<tr><td colspan="3">The kernel recorded no specific condition.</td></tr>'):
            self.assertIn(words, page)
        site = g2.build(WEBSITE)   # the evidence under the picture carries the plan's cost
        self.assertIn(html.escape(f'Kernel status PLAN_READY; plan cost {json.dumps(site["plan"]["cost"])}; trace root ', quote=True), site['files']['index.html'])
        def two_goals(n):
            p = copy.deepcopy(pack(n))
            return dict(p, goals=p['goals'] + ['other_goal']) if n == '60_standard_goal' else p
        with self.assertRaisesRegex(ValueError, 'The standard packs must leave exactly one standing goal'):   # the standard judges one goal, or the build is refused
            G.build_system(WEBSITE, g2.catalogue(), two_goals)

    # ---------------------------------------------------------------- C9: the record beside the page
    def test_record_json_holds_every_look_and_run_whole(self):
        for s in g2.demo():
            rec = json.loads(s['files']['record.json'])
            looks = [r for r in [rec.get('plan'), rec.get('after'), rec.get('standard'), rec.get('draft')] + rec.get('runs', []) + rec.get('no_runs', []) + rec.get('no_after', []) if r]
            self.assertTrue(looks and all(chain_ok(r) for r in looks), s['asked'])
            self.assertEqual(rec['schema'], 'core-algorithm/system-record/1')
            if s['verdict'] == 'NO_DOMAIN':
                self.assertEqual(sorted(rec), ['draft', 'schema'])
                continue
            run = s['model_run']
            self.assertEqual(sorted(rec), ['after', 'no_after', 'no_runs', 'plan', 'runs', 'schema', 'standard'], s['asked'])
            self.assertEqual(sorted(x['trace_root_sha256'] for x in looks), sorted(x['trace_root_sha256'] for x in G.looks(rec)), s['asked'])   # the looks kept in the record are all of them
            self.assertEqual(s['plan'], dict(G._brief(rec['plan']), goal=rec['plan']['goal'], scope=rec['plan']['scope']), s['asked'])
            self.assertEqual((run['path'], run['after'], run['goal_held']), ([G._brief(r) for r in rec['runs']], G._brief(rec['after']) if rec['after'] else None, G._held(rec['after']) if rec['after'] else None), s['asked'])
            self.assertEqual([a['if_yes'] for a in run['asks']], [G._brief(r) for r in rec['runs'][1:]], s['asked'])
            self.assertEqual([a['if_no'] for a in run['asks']], [dict(G._brief(r), goal_held=G._held(look) if look else None) for r, look in zip(rec['no_runs'], rec['no_after'])], s['asked'])
            self.assertEqual((rec['standard'] or {}).get('trace_root_sha256'), s['standard']['trace_root_sha256'], s['asked'])
            self.assertEqual(len(re.findall(r'<tr><td>\d+</td><td>[A-Z_]+</td><td><code>[0-9a-f]{16}</code></td></tr>', s['files']['index.html'])), len(rec['plan']['trace']), s['asked'])   # one row per decision of the first look
            for i, a in enumerate(run['asks']):   # the kernel's own chain says which answer closed the question on each path
                closed = lambda r: [(e['data']['receipt'], e['data']['truth'], e['data']['source']) for e in r['trace'] if e['operation'] == 'ASK_CLOSED']
                self.assertEqual((closed(rec['runs'][i + 1]), closed(rec['no_runs'][i])), ([(a['receipt_sha256'], 'TRUE', 'STAMP:' + a['to'])], [(a['receipt_sha256'], 'FALSE', 'STAMP:' + a['to'])]), s['asked'])
                self.assertEqual(rec['plan']['trace'][:-1], rec['runs'][0]['trace'][:len(rec['plan']['trace']) - 1], s['asked'])   # the first look's rows open the first run's chain
            self.assertIn(f'The record: {len(rec["plan"]["trace"])} decisions in a hash chain', s['files']['index.html'], s['asked'])
            self.assertIn(f'<code>{rec["plan"]["trace"][-1]["sha256"][:16]}</code></td></tr></table>', s['files']['index.html'], s['asked'])
            scenario_files = {p.stem for p in (ROOT / 'scenarios').glob('*.json')}
            self.assertTrue(all(p['pack'] in scenario_files for r in G.looks(rec) for p in r['provenance']), s['asked'])   # every look and run kept as a result ran on scenario files only

    def test_the_system_says_of_a_look_only_what_its_chain_carries(self):
        # Refuter round on the third build: the first look's proof lines, needs and branch stood in system.json and on the page, and no check holds them (no trace carries
        # them). They are cut from both: a system says of a look or run what its hash chain carries, and record.json keeps the kernel's results as it returned them.
        beside = {'needs', 'proof', 'selected_branch', 'goal_truth_before', 'goal_truth_after', 'candidates', 'pareto_options', 'provenance', 'trace'}
        def keys(v):
            if type(v) is dict:
                return set(v) | {k for x in v.values() for k in keys(x)}
            return {k for x in v for k in keys(x)} if type(v) is list else set()
        mod, v = check_module(), verifier()
        for s in g2.demo():
            if s['verdict'] == 'NO_DOMAIN':
                continue
            rec, system = json.loads(s['files']['record.json']), json.loads(s['files']['system.json'])
            self.assertEqual(sorted(s['plan']), sorted(['status', 'work_state', 'actions', 'pending', 'skipped', 'cost', 'stop_reasons', 'stopped', 'trace_root_sha256', 'receipts', 'goal', 'scope']), s['asked'])
            self.assertEqual(keys(system) & beside, set(), s['asked'])
            self.assertTrue({'needs', 'proof', 'selected_branch', 'goal_truth_before'} <= set(rec['plan']), s['asked'])   # record.json keeps the whole result
            self.assertNotIn('proof lines', s['files']['index.html'], s['asked'])
            # A stated limit, pinned: what a result says beside its trace is held by no check, and it reaches no other file. With it rewritten in record.json, the system
            # and the page that the independent checks work out from that record are the very texts the builder wrote.
            forged = copy.deepcopy(rec)
            for r in G.looks(forged):
                r.update(proof=['approved by the board'], needs=[], selected_branch='R-OTHER@9/OR7', goal_truth_before='TRUE', candidates=[{'id': 'x'}])
            chosen = None if s['choice']['how'] != 'the caller' else [r for r in g2.exhibits() if r['id'] == s['domain']['id']][0]
            again = mod['system_of'](s['asked'], [chosen] if chosen else g2.catalogue(), chosen, forged, {k: h['run'] for k, h in s['handlers'].items()}, pack, v.sha)
            self.assertEqual((mod['dump'](again), mod['page_of'](again, forged, G.CSS)), (s['files']['system.json'], s['files']['index.html']), s['asked'])

    def test_the_checks_work_every_system_and_page_out_again(self):
        # Refuter round on the third build: a page was held in parts (first screen, footer, picture, question) and everything between the parts was free; a third of
        # system.json's leaves (the generated workflow, its atoms, the scaffold) were compared with nothing but themselves. The independent checks now write the system
        # and the page a second time, from the kernel's results and the pack files, and compare both whole. Here the second writing is held to the builder beyond the
        # ten systems on record: where it has words they are the builder's, byte for byte; where it has none it says so and writes nothing.
        mod, v = check_module(), verifier()
        def again(s, cat, row, load):
            rec = json.loads(s['files']['record.json'])
            if 'draft' in rec:
                rec = {'schema': 'core-algorithm/system-record/1', 'draft': mod['draft_of'](s['asked'], v.sha)[1]}
                self.assertEqual(mod['dump'](rec), s['files']['record.json'], s['asked'])   # the draft's one look, made from the words: four rows, their hashes, the whole result
            system = mod['system_of'](s['asked'], cat, row, rec, {k: h['run'] for k, h in s['handlers'].items()}, load, v.sha)
            return mod['dump'](system), mod['page_of'](system, rec, G.CSS)
        rows, shown = g2.catalogue(), g2.exhibits()
        for i, s in enumerate(g2.demo()):
            chosen = None if i < 6 else shown[i - 6]
            self.assertEqual(again(s, [chosen] if chosen else rows, chosen, pack), (s['files']['system.json'], s['files']['index.html']), s['asked'])
        ask = lambda **kw: m('ask-ok', 'approved', 'ask', ASK, ask_to='customer', **kw)
        routes = [('done', [['shipped'], ['refunded']])]
        worlds = {   # other states than the ten on record: the first eight are states the second writing has words for
         'one step': world(['done'], methods=[m('mk', 'done')]),
         'already true': world(['done'], methods=[m('mk', 'done')], evidence=[row('done')]),
         'a planned question already answered at its turn': world(['shipped'], methods=[m('prepare-quote', 'quote'), m('ask-approval', 'approved', 'ask', ASK, req=['quote'], ask_to='customer'),
                                                                                   m('ship', 'shipped', req=['quote', 'approved'])],
                                                              evidence=[row('approved', depends_on=[{'predicate': 'quote', 'version': 'local-sim-1'}])]),
         'two methods for one fact': world(['done'], [('done', [['y', 'z']])], [m('u1', 'u', cost={'compute': 0}), m('u2', 'u', cost={'compute': 0}), m('y', 'y', req=['u']), m('z', 'z', req=['u'])]),
         'the question is the last step': world(['done'], [('done', [['a', 'ok']])], [m('mk-a', 'a'), m('ask-ok', 'ok', 'ask', ASK, ask_to='owner', req=['a'])]),
         'a no that takes another route': world(['done'], routes, [ask(), m('ship', 'shipped', req=['approved']), m('refund', 'refunded', cost={'compute': 5, 'money': 5, 'attention': 0})]),
         'a fan of arrows': world(['done'], [('done', [['e1', 'e2', 'e3']])], [m('first', 'a'), m('second', 'b', req=['a']), m('third', 'c', req=['b']), m('x1', 'e1', req=['a', 'c']),
                                                                             m('x2', 'e2', req=['a', 'b', 'c']), m('x3', 'e3', req=['a'])]),
         'no plan left after a yes': world(['G'], [('G', [['c'], ['q']])], [m('ask-q', 'q', 'ask', ASK, ask_to='owner')], [row('G', 'FALSE')]),
         'two questions': self._asks(2),
         'a decision stands against it': world(['done'], methods=[m('ship', 'done', req=['export_ok'])], evidence=[row('export_ok', 'FALSE', final=True, source='policy/export-control')]),
         'a stop after a yes': world(['shipped'], methods=[m('ask-ok', 'ok', 'ask', ASK, ask_to='customer'), m('cand', 'c', 'compile_candidate', constructor='none'), m('ship', 'shipped', req=['ok', 'c'])]),
         'a no after which the other route asks': world(['done'], routes, [ask(), m('ship', 'shipped', req=['approved']), m('ask-boss', 'boss_ok', 'ask', ASK, ask_to='boss'),
                                                                          m('refund', 'refunded', cost={'compute': 5, 'money': 5, 'attention': 0}, req=['boss_ok'])]),
         'another route after the yes': world(['G'], [('G', [['packed', 'paid']])], [m('ask-payer', 'paid', 'ask', ASK, ask_to='payer'), m('pack-a', 'packed'),
                                                                                   m('pack-b', 'packed', 'compile_candidate', req=['paid'], constructor='none')]),
         'the gate turns the plan away': world(['done'], [('done', [['a', 'b']])], [m('mk-a', 'a'), m('mk-b', 'b', grant='other')]),
         'nobody wrote down what the goal means': world(['done']),
         'a circle': world(['a'], methods=[m('ma', 'a', req=['b']), m('mb', 'b', req=['a'])])}
        same, none = [], []
        for name, w in worlds.items():
            s = build(w)
            try:
                got = again(s, [{'id': 'w', 'title': 'W', 'goal': w['goals'][0], 'say': 'ship it', 'words': ['ship'], 'packs': ['w']}], None, lambda n, w=w: copy.deepcopy(w) if n == 'w' else pack(n))
            except mod['NoWords']:
                none.append(name)
                continue
            self.assertEqual(got, (s['files']['system.json'], s['files']['index.html']), name)
            same.append(name)
        self.assertEqual((same, none), (list(worlds)[:8], list(worlds)[8:]))
        # A stated limit, pinned: whether a step's effect holds after the run is the builder's own finding (the record keeps no stored rows). The second writing lists no
        # such step, so a system that lists one is not the text it works out: on record it would be refused, and a step the builder left out would not be found.
        goal = pack('30_build_goal')['goals'][0]
        entry = {'id': 'build', 'title': 'Builder', 'goal': goal, 'say': 'build it', 'words': ['build'], 'packs': ['30_build_goal', '31_build_theory', '32_builder_components']}
        s = G.build_system('build it', [entry], pack)
        self.assertEqual(s['model_run']['effects_missing'], ['construct-enquiry-candidate@1'])
        self.assertNotEqual(again(s, [entry], None, pack)[0], s['files']['system.json'])
        # every leaf of a system is held: with any one of them changed, system.json is no longer the text worked out (here: every leaf of the smallest built system)
        s = g2.demo()[6]
        base = json.loads(s['files']['system.json'])
        def leaves(x, at=()):
            if type(x) is dict:
                for k, y in x.items():
                    yield from leaves(y, at + (k,))
            elif type(x) is list:
                for k, y in enumerate(x):
                    yield from leaves(y, at + (k,))
            else:
                yield at
        worked, changed = again(s, [shown[0]], shown[0], pack)[0], 0
        for at in leaves(base):
            forged = copy.deepcopy(base)
            node = forged
            for k in at[:-1]:
                node = node[k]
            node[at[-1]] = (not node[at[-1]]) if type(node[at[-1]]) is bool else node[at[-1]] + 1 if type(node[at[-1]]) is int else 'x' if node[at[-1]] is None else node[at[-1]] + ' x'
            self.assertNotEqual(mod['dump'](forged), worked, at)
            changed += 1
        self.assertEqual((worked, changed > 150), (s['files']['system.json'], True))

    def test_a_page_is_tags_and_text_and_nothing_else(self):
        # Refuter round on the third build: the checks read a page with the interpreter's tolerant parser, which ends a comment and reads an end tag otherwise than a
        # browser does. They now read a page strictly: after the doctype tags and text, every tag in one of three shapes, no comment, no declaration, no stray bracket.
        mod = check_module()
        strict = lambda page: mod['markup_of'](page.replace(G.CSS, '', 1))
        for s in g2.demo():
            tags_, attrs = strict(s['files']['index.html'])
            self.assertEqual((tags_ - mod['TAGS'], {k for _, k, _ in attrs} - mod['ATTRS']), (set(), set()), s['asked'])
        page = g2.build(WEBSITE)['files']['index.html']
        for forged in (page.replace('<h2>The plan</h2>', '<h2>The plan</h2><!-- a comment -->'), page.replace('<h2>The plan</h2>', '<h2>The plan</h2><!-- -- >'),
                       page.replace('<footer>', '<![CDATA[<footer>'), page.replace('<h2>Files</h2>', '<!doctype html><h2>Files</h2>'), page.replace('<h2>Files</h2>', '<?php x ?><h2>Files</h2>'),
                       page.replace('<h2>The plan</h2>', '<h2>The plan</h2><svg/onload=alert(1)>'), page.replace('<h2>Files</h2>', '<h2>Files</h2><a href=//example.com/x>more</a>'),
                       page.replace('<h2>Files</h2>', "<h2>Files</h2><a href='x'>more</a>"), page.replace('<h2>Files</h2>', '<h2>Files</h2>a < b'), page.replace('<h2>Files</h2>', '<h2>Files</h2>a > b'),
                       page.replace('</h1>', '</h1 >'), page.replace('<h1>', '<H1>'), page.replace('</h1>', '</h1 class="x">'), page.replace('<h2>Files</h2>', '<h2 class="a"class="b">Files</h2>'),
                       page.replace('<!doctype html>', '<!DOCTYPE html>'), ' ' + page, page.replace('<h2>Files</h2>', '<h2\n>Files</h2>')):
            self.assertNotEqual(forged, page)
            self.assertIsNone(strict(forged), forged[:80])
        self.assertEqual(re.findall(r'html\.parser|HTMLParser', (ROOT / 'qa' / 'checks' / 'system.py').read_text(encoding='utf-8')), [])   # the tolerant parser is no part of the checks any more

    def test_the_independent_checks_hold_the_record_and_refuse_forgeries(self):
        data = recorded()
        if data is None:
            self.skipTest('results/actual_run_records.json is generated by tools/run_all.py')
        v, mod = verifier(), check_module()
        run = lambda d: [name for name, ok, _ in mod['checks'](d, ROOT, v.sha, v.check_chain) if not ok]
        self.assertEqual(([cid for cid, _, _ in mod['checks'](data, ROOT, v.sha, v.check_chain)], run(data)), (MINE, []))
        self.assertIn(f'{mod["FORGED"]} forgeries', (ROOT / 'README.md').read_text(encoding='utf-8'))   # the number the passage quotes is the number the checks pin
        S = lambda d: d['scenes']['system']['systems']
        fsha = lambda t: hashlib.sha256(t.encode('utf-8')).hexdigest()
        def sealed(d):   # what a forger does after a change: the system's digest, the page's quote of it, the manifest, the folder's name, and what the command is said to have written
            for e in S(d):
                s = json.loads(e['files']['system.json'])
                old = s['system_sha256']
                s['system_sha256'] = digest({k: x for k, x in s.items() if k != 'system_sha256'})
                e['files'].update({'index.html': e['files']['index.html'].replace(old, s['system_sha256']), 'system.json': json.dumps(s, indent=2, ensure_ascii=False) + '\n'})
                e['files']['manifest.json'] = json.dumps({'schema': 'core-algorithm/system-manifest/1', 'system_sha256': s['system_sha256'],
                                                         'files': {n: fsha(t) for n, t in e['files'].items() if n != 'manifest.json'}}, indent=2, sort_keys=True) + '\n'
                e['folder'] = e['folder'][:-16] + fsha(e['files']['manifest.json'])[:16]
            first = S(d)[0]
            want = {first['folder'] + '/' + n: fsha(t) for n, t in first['files'].items()}
            for i, x in enumerate(d['scenes']['system']['command']):
                x['written'] = dict(want) if i in (0, 1, 4) else dict(want, **{first['folder'] + '/notes.txt': fsha('mine')})
                x['stdout'] = [line[:line.index('<out>/')] + '<out>/' + first['folder'] + '/index.html' for line in x['stdout']]
                x['stderr'] = [line if '<out>/' not in line else 'g2.py: error: <out>/' + first['folder'] + line[line.index(' already holds'):] for line in x['stderr']]
            return d
        def forged(change, seal=True):
            d = dict(data, scenes=dict(data['scenes'], system=json.loads(json.dumps(data['scenes']['system']))), cases=json.loads(json.dumps(data['cases'])))
            change(d)
            return sealed(d) if seal else d
        self.assertEqual(run(forged(lambda d: None)), [])   # an honest copy, sealed again, passes
        page = lambda i, old, new: lambda d: S(d)[i]['files'].update({'index.html': S(d)[i]['files']['index.html'].replace(old, new, 1)})
        def system(i, change):
            def go(d):
                s = json.loads(S(d)[i]['files']['system.json'])
                change(s)
                S(d)[i]['files'].update({'system.json': json.dumps(s, indent=2, ensure_ascii=False) + '\n', 'scaffold.json': json.dumps(s['implementation']['scaffold'], indent=2, ensure_ascii=False) + '\n',
                                         'atoms.json': json.dumps(s['implementation']['atoms'], indent=2, ensure_ascii=False) + '\n'})
            return go
        case = lambda d, cid: [c for c in d['cases'] if c['id'] == cid][0]
        picture = re.search(r'<div class="scroll"><svg class="plan".*?</svg></div>', S(data)[1]['files']['index.html'], re.S).group(0)
        hidden = '<div class="choice"><div class="panel">' + picture + '</div></div>'
        for what, change, seal, expect in (
                ('a page with other words', page(0, 'Ready: 4 steps in order', 'Done: 4 steps ran for real'), True, [MINE[3]]),
                ('a page that hides its tags', page(0, '.tag{display:inline-block;', '.tag{display:none;'), True, [MINE[3]]),
                ('another title', page(0, f'<title>{WEBSITE}</title>', '<title>APPROVED AND LIVE</title>'), True, [MINE[3]]),
                ('another chooser said before the plan', page(0, 'chosen by a word match on organisation, website (a stand-in: a person or an agent should confirm the choice).</p><h2>The plan</h2>',
                                                              'chosen by the owner.</p><h2>The plan</h2>'), True, [MINE[3]]),
                # the forgeries of the refuter round on the third build: each passed every check of that build
                ('the picture hidden by the page\'s own style sheet', page(1, picture, '<p>Approved: both steps have run and the replacement is on its way.</p>' + hidden), True, [MINE[3]]),
                ('a box of the picture that carries other words', page(1, '>Ship the replacement</text>', '>Refund the customer</text>'), True, [MINE[3]]),
                ('a comment a browser does not end', page(0, '<h2>The plan</h2>', '<h2>The plan</h2><!-- -- >'), True, [MINE[3]]),
                ('the footer in a folded part', page(0, '<footer>', '<details><summary>more</summary><table><tr><td></details></td></tr></table><footer>'), True, [MINE[3]]),
                ('the box marked stops here renamed', page(7, '>Construct the candidate</text>', '>Validate the field</text>'), True, [MINE[3]]),
                ('an arrow pointed at another box', page(0, 'L187,7 L492,7 L492,24"/><polygon class="head" points="492,30 488,23 496,23"', 'L187,7 L706,7 L706,24"/><polygon class="head" points="706,30 702,23 710,23"'), True, [MINE[3]]),
                ('a second verdict box', page(8, '<h2>What stands in the way</h2>', '<div class="verdict READY"><p>Ready: 2 steps in order, and nothing waits on anyone.</p></div><h2>What stands in the way</h2>'), True, [MINE[3]]),
                ('a sentence put between two parts of a page', page(0, '<h2>What done means</h2>', '<p>Approved by the board.</p><h2>What done means</h2>'), True, [MINE[3]]),
                ('a rule of the scaffold, the purpose and the atoms\' constraints rewritten',
                 system(1, lambda s: (s['implementation']['scaffold']['rules'].__setitem__(0, {'tag': 'go', 'line': 'any step may run without a grant and without asking anyone'}),
                                      s['implementation']['scaffold'].update(purpose='run everything for real'), [a.update(constraints=['no grant needed']) for a in s['implementation']['atoms']])), True, [MINE[2], MINE[3]]),
                ('a look beside the files that is not the one in record.json', lambda d: S(d)[1]['looks']['runs'][1].update(status='LOCAL_MODEL_EFFECTS_RECORDED'), False, [MINE[1]]),
                ('a folder named after other words', lambda d: S(d)[0].update(folder='a-website-for-my-organisation'), False, [MINE[0], MINE[5]]),
                ('a refusal told as a success', lambda d: d['scenes']['system']['command'][2].update(exit=0), False, [MINE[5]]),
                ('a traceback', lambda d: d['scenes']['system']['command'][3]['stderr'].append('Traceback'), False, [MINE[5]]),
                ('a write that could not be reported told as a refusal', lambda d: d['scenes']['system']['command'][4].update(exit=2), False, [MINE[5]]),
                ('case 70 told as ready', lambda d: case(d, '70_recorded_open')['outcome'].update(status='PLAN_READY'), False, [MINE[6]]),
                ('case 70 with another budget', lambda d: case(d, '70_recorded_open')['derived_state']['budget_after'].update(attention=3), False, [MINE[6]]),
                ('case 71 told as ready', lambda d: case(d, '71_no_plan_after_a_yes')['outcome'].update(status='PLAN_READY'), False, [MINE[7]]),
                # refuter round on the third build (refuter 2, finding 4): what a case says beside its runs passed every check of that build
                ('case 70 with another world view of the desk\'s row', lambda d: case(d, '70_recorded_open')['four_views']['world'][-1].update(truth='TRUE', source='fixture/reviewed'), False, [MINE[6]]),
                ('case 70 in another scope', lambda d: case(d, '70_recorded_open').update(scope='orgB/fulfillment'), False, [MINE[6]]),
                ('case 70 with other needs, in both copies of its run', lambda d: [r.update(needs=[]) for r in (case(d, '70_recorded_open')['outcome'], case(d, '70_recorded_open')['run']['runs'][0])], False, [MINE[6]]),
                ('case 71 with another rule in its knowledge view', lambda d: case(d, '71_no_plan_after_a_yes')['four_views']['knowledge'][0]['branches'].pop(0), False, [MINE[7]]),
                ('the first sentence of the system of case 71 naming the first reason of the trace',
                 page(9, 'the kernel has no plan left, because the facts contradict each other (the order is closed).', 'the kernel has no plan left, because a needed fact is unknown and nothing may ask for it (a refund is on record).'),
                 True, [MINE[3], MINE[7]])):
            self.assertEqual(run(forged(change, seal)), expect + [FORGERY_ROW], what)   # the rows that refuse it, and the forgery row, which does not vouch for a record that fails
        # and the verifier itself holds every look kept as a result to its trace and its packs, like any other run (S201, by the rule of S42), also when the sequence is sealed again
        d = forged(lambda d: S(d)[1]['looks']['runs'][1].update(status='LOCAL_MODEL_EFFECTS_RECORDED'), False)
        d['added'] = dict(d['added'], scenes=dict(d['added']['scenes'], system=v.sha(d['scenes']['system'])))
        failed = {t['id']: t['detail'] for t in v.inspect(d)['checks'] if not t['pass']}
        self.assertEqual(failed.get(S201), 'system: run 6 does not agree with its trace and its packs')   # that one sentence and no other: the seal, the names and every other run of the sequence hold
        self.assertEqual([name for name in MINE if name in failed], [MINE[1], FORGERY_ROW])   # of this version's rows: the looks beside the files are not those of record.json, and the forgery row does not vouch for it
        got, why = v.module_rows(ROOT / 'qa' / 'checks' / 'system.py', data, ROOT, set())   # the module as the verifier takes it in: its text passes the parser, it runs on a copy of the record, and its rows are in shape
        self.assertEqual((why, [(cid, ok) for cid, ok, _ in got]), (None, [(name, True) for name in MINE]))
        self.assertEqual(sorted(v.number(name) for name in MINE), list(range(120, 129)))   # the numbers this version was given: S120 to S129

    def test_each_comparison_of_the_checks_is_the_one_that_refuses_its_own_forgeries(self):
        # S127 lists every forgery under the row that must refuse it, and names each one that row lets through. With one comparison switched off in the text of the
        # check module, the forgeries made for that comparison get through and the honest record still passes: no comparison is carried by another.
        data = recorded()
        if data is None:
            self.skipTest('results/actual_run_records.json is generated by tools/run_all.py')
        v, path = verifier(), ROOT / 'qa' / 'checks' / 'system.py'
        src = path.read_text(encoding='utf-8')
        def let_through(old, new):
            self.assertEqual(src.count(old), 1, old)
            ns = {}
            exec(compile(src.replace(old, new), str(path), 'exec'), ns)
            rows = {cid: (ok, detail) for cid, ok, detail in ns['checks'](data, ROOT, v.sha, v.check_chain)}
            self.assertEqual([rows[name][0] for name in MINE[:8]], [True] * 8, old)   # the honest record passes either way
            return 0 if rows[FORGERY_ROW][0] else len(re.findall(r"'(?:un)?sealed \d+ ", rows[FORGERY_ROW][1]))
        pins = ("                    and same([[[x['method'] for x in r['receipts']] for r in runs_of(s)] if 'model_run' in s else None for s in got], RAN) and same([s.get('blocked_at') for s in got], WAY)\n"
                "                    and all(not r['skipped'] and all(x['status'] == 'LOCAL_ONLY' for x in r['receipts']) for s in got for r in runs_of(s))   # no step was skipped, and every receipt is local only\n")
        self.assertEqual(let_through('files[\'index.html\'] == page_of(s, rec, style[0]) and markup is not None', 'files[\'index.html\'] == page_of(s, rec, style[0]) and markup is not None '), 0)   # the module as it is lets none through
        for what, old, new, count in (('the page, compared whole', "files['index.html'] == page_of(s, rec, style[0]) and markup is not None", 'markup is not None', PAGE_COUNT),
                                      ('system.json, compared whole', "out['system'] = files['system.json'] == dump(s)", "out['system'] = True", SYSTEM_COUNT),
                                      ('what the ten systems say ran, and that no step was skipped', pins, '', 1),
                                      ('the recorded case behind every domain', "                                      and any(c['outcome']['trace_root_sha256'] in roots for c in d['cases'] if c['packs'] == chosen['packs'] and c['outcome']))",
                                       '                                      )', 5),
                                      ('the look at a draft, made here from the words', "out['record'] = files['record.json'] == dump(rec) and 'looks' not in e", "out['record'] = 'looks' not in e", 3),
                                      ('the style sheet', "fsha(style[0]) == STYLE_SHA256 and ", '', 3),
                                      ('the keys of a result', "set(r) <= RESULT_KEYS and ", '', 1),
                                      ('the part files', "                and all(files[name] == dump(part) for name, part in parts.items()))", '                )', 4),
                                      ('the folder\'s name', "and e['folder'] == slug(s['asked']) + '-' + fsha(files['manifest.json'])[:16] and", 'and', 3),
                                      ('what a run cost', "and same(chosen[0]['full_cost'], total(chosen[0]['actions'])) and same(r['cost'], total(r['actions']))", '', 1),
                                      ('which answer closed the question, in the kernel\'s own chain', " and closed(yes, 'TRUE') and closed(no, 'FALSE')", '', 1),
                                      ('the looks kept beside the files', "and same(e['looks']['runs'], looks_of(rec))", '', 3),
                                      ('what cases 70 and 71 say beside their runs', "        b, rows, r = books(packs), stored(packs), c['outcome']\n        return (",
                                       "        b, rows, r = books(packs), stored(packs), c['outcome']\n        return True or (", 17)):
            self.assertEqual(let_through(old, new), count, what)

    # ---------------------------------------------------------------- C4 and C10: the catalogue, the exhibits and the cases
    def test_every_catalogue_and_exhibit_row_is_a_recorded_case(self):
        recorded_cases = {}
        for c in CASES:   # the first case recorded on a list of packs (another version may record the same packs once more)
            recorded_cases.setdefault(tuple(c[3]), c)
        rows, shown = g2.catalogue(), g2.exhibits()
        self.assertEqual(([r['id'] for r in rows], [recorded_cases[tuple(r['packs'])][0] for r in rows]), (['website', 'order', 'enquiry', 'workflow-standard'], ['28_website', '29_ask', '14_privacy_method', '26_registrable_repair']))
        self.assertEqual(([r['id'] for r in shown], [recorded_cases[tuple(r['packs'])][0] for r in shown]),
                         (['order-nobody-may-ask', 'builder-without-constructor', 'order-recorded-open', 'order-closed-on-confirmation'], ['02_methods', '30_stop', '70_recorded_open', '71_no_plan_after_a_yes']))
        for r in rows + shown:
            case = recorded_cases[tuple(r['packs'])]
            self.assertEqual(State.from_packs([pack(n) for n in r['packs']]).goals, [r['goal']], r['id'])
            methods = {x['id'] for n in r['packs'] for x in pack(n).get('methods', [])}
            self.assertTrue(methods | {r['goal']} <= set(r['labels']), r['id'])   # the page has plain words for the goal and for every step
            s = G.build_system(r['say'], [r], pack, r['id'])
            ran = Kernel(State.from_packs([pack(n) for n in r['packs']])).run_standing(execute=case[4])['runs'][0]   # the case, as tools/run_all.py runs it
            self.assertIn(ran['trace_root_sha256'], [s['plan']['trace_root_sha256']] + [x['trace_root_sha256'] for x in s['model_run']['path'][:1]], r['id'])
        self.assertEqual([s['verdict'] for s in (exhibit(0), exhibit(1), exhibit(2), exhibit(3))], ['BLOCKED', 'NOT_READY', 'NOT_READY', 'NOT_READY'])
        state = State.from_packs([pack(n) for n in shown[2]['packs']])   # case 70 at the kernel: the first look waits and ships nothing; the yes ships; the next look is a conflict
        opened = Kernel(state)
        first = opened.run_standing(execute=True)['runs'][0]
        self.assertEqual((first['status'], first['actions'], first['pending'], first['goal_truth_after'], dict(state.budget)),
                         ('WAITING', ['ask-customer-approval@1'], ['ship-replacement@1'], 'FALSE', {'compute': 10, 'money': 10, 'attention': 2}))
        yes = answer(opened, first['model_receipts'][0], 'TRUE', 'customer', execute=True)['runs'][0]
        again = opened.run_standing(execute=False)['runs'][0]
        self.assertEqual((yes['status'], yes['actions'], again['status'], again['actions'], state.fact('order_complete')['source']),
                         ('LOCAL_MODEL_EFFECTS_RECORDED', ['ship-replacement@1'], 'EVIDENCE_CONFLICT', [], 'fixture/order-desk'))

    # ================================================================ the confirming round: two refuters on the build laid on the promoted base
    # No finding blocked release, and each is settled without new code (rulings R19 and R34 of the program): a limit is stated in the README and pinned here as
    # it stands today (the tests named test_limit_...), a claim is tied to the unit test that holds it, and every single mutation of the builder that changed
    # what a page, a system or a refusal says while no test failed now fails an assertion (the four tests after the limits). What a finding proposed as new code
    # is owed to the next version of the page builder; NEXT-GATES.md names it.

    def _process(self, argv, where, standard_output='read'):
        """The command as a process of its own, as a person runs it from a shell, with `where` as its working folder. standard_output is 'read' (read here),
        'reader gone' (a pipe whose reader has gone, as in `g2.py ... | head -0`) or 'closed' (closed before the start, as in `g2.py ... >&-`).
        Returns the exit code, what was printed (None when nobody reads) and the lines on standard error."""
        cmd = [sys.executable, '-I', '-B', str(ROOT / 'extensions' / 'g2.py')] + argv
        if standard_output == 'reader gone':
            reader, writer = os.pipe()
            os.close(reader)
            try:
                done = subprocess.run(cmd, stdout=writer, stderr=subprocess.PIPE, cwd=str(where), timeout=300)
            finally:
                os.close(writer)
            return done.returncode, None, done.stderr.decode('utf-8').splitlines()
        if standard_output == 'closed':
            cmd = ['/bin/sh', '-c', 'exec "$0" "$@" >&-'] + cmd
        done = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=str(where), timeout=300)
        return done.returncode, done.stdout.decode('utf-8'), done.stderr.decode('utf-8').splitlines()

    @unittest.skipUnless(os.name == 'posix' and os.path.exists('/bin/sh'), 'the command is run from a POSIX shell here')
    def test_limit_as_a_process_of_its_own_the_command_ends_otherwise_than_main(self):
        # Confirming round, refuter 1, finding 1. A call that wrote and could not say so is one line and exit code 3 where main() is called inside one process with a
        # stand-in for standard output: that is what S125's fifth recorded run and test_a_call_that_wrote_ends_with_another_exit_code_than_a_refusal hold. Run as a
        # process of its own the command ends otherwise, and this is how it ends today (Python 3.9 and 3.11 alike; only the length of a traceback differs). Owed to
        # the next version: standard output pointed away when the line cannot be printed, a closed standard output read as one that cannot print, and the fifth run
        # recorded from a process.
        site = g2.build(WEBSITE)
        mine = {n: text_.encode('utf-8') for n, text_ in site['files'].items()}
        on_disk = lambda d: {p.name: p.read_bytes() for p in d.iterdir()}
        with tempfile.TemporaryDirectory() as t:
            t = Path(t).resolve()
            built = lambda name, how: self._process(WEBSITE.split() + ['--out', str(t / name)], t, how)
            code, out, err = built('read', 'read')   # with a reader: every file, one line that says where, exit code 0
            self.assertEqual((code, out, err, on_disk(t / 'read' / site['folder'])), (0, f'READY      {WEBSITE}  ->  {t / "read" / site["folder"]}/index.html\n', [], mine))
            code, _, err = built('gone', 'reader gone')
            self.assertEqual((code, len(err), err[:1]), (120, 3, [f'g2.py: error: 1 of 1 folders were written under {t / "gone"}, and the line that says so could not be printed (BrokenPipeError)']))
            self.assertTrue(err[1].startswith('Exception ignored') and err[2].startswith('BrokenPipeError'), err)   # main() left with code 3; the interpreter then fails once more when it flushes standard output at exit, says so in two lines of its own and ends with 120
            self.assertEqual(on_disk(t / 'gone' / site['folder']), mine)   # every file was written
            code, out, err = built('closed', 'closed')
            self.assertEqual((code, out, err[:1], err[-1:]), (1, '', ['Traceback (most recent call last):'], ["AttributeError: 'NoneType' object has no attribute 'flush'"]))
            self.assertEqual(on_disk(t / 'closed' / site['folder']), mine)   # every file was written before the traceback
            code, _, err = self._process(['--list'], t, 'reader gone')   # --list writes nothing, and main() calls a line it cannot print a refusal: as a process it is 120 and three lines as well
            self.assertEqual((code, len(err), err[:1]), (120, 3, ['g2.py: error: [Errno 32] Broken pipe']))
            code, _, err = self._process(['a', 'site', '--domain', 'nobody-reviewed-this', '--out', str(t / 'refused')], t, 'reader gone')
            self.assertEqual((code, err, (t / 'refused').exists()), (2, ['g2.py: error: Unknown domain: pick one from the catalogue'], False))   # a refusal prints nothing on standard output: one line and exit code 2 as a process too

    def test_limit_a_link_loop_as_the_output_folder_is_pythons_error_not_a_refusal(self):
        # Confirming round, refuter 1, finding 3 (a note). --out is resolved before anything is looked at. Where Python's pathlib answers a link that leads back to
        # itself with a RuntimeError (3.9 and 3.11 do, each naming the path it stopped at), main() lets that error through: nothing is written and no line of the
        # command's own is printed; as a process that is a traceback and exit code 1. Owed to the next version: that error caught around the resolve of --out,
        # one line, exit code 2.
        with tempfile.TemporaryDirectory() as t:
            t = Path(t).resolve()
            loop, real = t / 'loop', t / 'real'
            real.mkdir()
            try:
                loop.symlink_to(loop)   # a link that points at itself
                (t / 'link').symlink_to(real, target_is_directory=True)
            except OSError:
                self.skipTest('this machine makes no links')
            try:
                loop.resolve()
            except RuntimeError as known:
                self.assertIn('Symlink loop from', str(known))
            except OSError:
                self.skipTest('this interpreter answers a link loop with an OSError, which the command refuses in one line')
            else:
                self.skipTest('this interpreter resolves a link loop without an error of its own, so the command gets as far as its own refusals')
            for out in (loop, loop / 'deeper'):   # the loop as the folder, and on the way to it
                said, complained = io.StringIO(), io.StringIO()
                with self.assertRaises(RuntimeError) as stop, contextlib.redirect_stdout(said), contextlib.redirect_stderr(complained):
                    g2.main(['a', 'site', '--out', str(out)])
                self.assertIn('Symlink loop from', str(stop.exception))
                self.assertEqual((said.getvalue(), complained.getvalue()), ('', ''), out)
            self.assertEqual((sorted(p.name for p in t.iterdir()), list(real.iterdir())), (['link', 'loop', 'real'], []))   # nothing was written
            if os.name == 'posix':
                code, out, err = self._process(['a', 'site', '--out', str(loop)], t)
                self.assertEqual((code, out, err[:1]), (1, '', ['Traceback (most recent call last):']))
                self.assertTrue(err[-1].startswith('RuntimeError: Symlink loop from'), err)
            site = g2.build('a site')   # a link that is no loop is another matter: --out is taken as given, and a link to a folder is followed
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(g2.main(['a', 'site', '--out', str(t / 'link')]), 0)
            self.assertEqual([p.name for p in real.iterdir()], [site['folder']])

    def test_limit_the_table_gives_a_recipe_to_a_row_that_unblocks_nothing(self):
        # Confirming round, refuter 1, finding 2. After the yes of case 71 the kernel has no plan left and gives two reasons. The first sentence names the one the
        # kernel names the run with (the conflict), but the table under it lists every row of the trace with the fixed recipe of its reason, the unknown refund
        # first: a verified fact for this condition, or a reviewed method that may ask for it. For this State neither unblocks anything: the confirmed branch already
        # closes the rule against the desk's row. The checks carry the same recipes, so S123 agrees with the page by construction. Owed to the next version: on a
        # look that one reason ends alone, the other reasons listed apart and without a recipe.
        closing = exhibit(3)
        self.assertEqual(closing['blocked_at'], [{'reason': 'QUERY_EVIDENCE', 'at': ['refund_recorded'], 'detail': None}, {'reason': 'EVIDENCE_CONFLICT', 'at': ['order_closed'], 'detail': None}])
        self.assertIn('<h2>What stands in the way</h2><div class="scroll"><table><tr><th>Where</th><th>Reason</th><th>What would unblock it</th></tr>'
                      '<tr><td>A refund is on record <code>refund_recorded</code></td><td>A needed fact is unknown and nothing may ask for it</td>'
                      '<td>A verified fact for this condition, or a reviewed method that may ask for it</td></tr>'
                      '<tr><td>The order is closed <code>order_closed</code></td><td>The facts contradict each other</td>'
                      '<td>Someone settling which fact is right: the stored row, or the conditions that say otherwise</td></tr></table></div>', closing['files']['index.html'])

        def after_the_yes():   # case 71 at the kernel, as the builder runs it: asked, and answered yes by the customer
            state = G._state([pack('173_closed_on_confirmation')], {k: dict(ACTIONS[k]) for k in G.KINDS})
            kernel = Kernel(state)
            first = kernel.run_standing(execute=True)['runs'][0]
            return state, kernel, answer(kernel, first['model_receipts'][0], 'TRUE', 'customer', execute=True)['runs'][0]
        _, _, yes = after_the_yes()
        self.assertEqual((yes['status'], yes['stop_reasons']), ('EVIDENCE_CONFLICT', ['EVIDENCE_CONFLICT', 'QUERY_EVIDENCE']))
        for truth, reasons in (('TRUE', ['EVIDENCE_CONFLICT']), ('FALSE', ['EVIDENCE_CONFLICT', 'METHOD_ABSENT'])):   # the first half of the recipe, followed: a verified fact for the refund
            _, kernel, _ = after_the_yes()
            run = kernel.on_event({'predicate': 'refund_recorded', 'truth': truth, 'verified': True, 'source': 'fixture/desk', 'version': '2'}, execute=True)['runs'][0]
            look = kernel.run_standing(execute=False)['runs'][0]
            self.assertEqual((run['status'], run['stop_reasons'], look['status'], look['actions']), ('EVIDENCE_CONFLICT', reasons, 'EVIDENCE_CONFLICT', []), truth)
        state, kernel, _ = after_the_yes()   # the second half, followed: a reviewed method that may ask for the refund
        state.apply({'schema': 'sutra-extension/2', 'id': 'a_method_that_may_ask_for_the_refund', 'scope': 'orgA/closing', 'grants': ['action:ask-desk-refund@1'],
                     'methods': [m('ask-desk-refund@1', 'refund_recorded', 'ask', ASK, ask_to='desk', question='Was a refund recorded?', provider='owner-channel', grant='action:ask-desk-refund@1')]})
        look = kernel.run_standing(execute=False)['runs'][0]
        self.assertEqual((look['status'], look['stop_reasons'], look['actions']), ('EVIDENCE_CONFLICT', ['EVIDENCE_CONFLICT'], []))

    # ---------------------------------------------------------------- three limits of the independent checks (confirming round, refuter 2, findings 1, 2 and 4)
    def _rows(self, d, v, whole=False):
        """The names of this version's rows that fail on a record. Without `whole`, the eight rows that read the record as it stands (S120 to S126 and S128);
        with it also S127, which reads those eight on its forged copies of the record handed in."""
        mod = check_module()
        if not whole:
            mod['forgeries_row'] = lambda *given: (FORGERY_ROW, True, 'not run here')
        return [name for name, ok, _ in mod['checks'](d, ROOT, v.sha, v.check_chain) if not ok]

    def _sealed(self, d, v):
        """What a forger does after a change, as the checks' own forgers do: each system's digest and the page's quote of it, the manifest, the folder's name, what
        the command is said to have written and printed, and the seal the add-on base keeps for the sequence."""
        mod = check_module()
        fsha = lambda text_: hashlib.sha256(text_.encode('utf-8')).hexdigest()
        systems = d['scenes']['system']['systems']
        for e in systems:
            s = json.loads(e['files']['system.json'])
            old = s['system_sha256']
            s['system_sha256'] = v.sha({k: x for k, x in s.items() if k != 'system_sha256'})
            e['files'].update({'index.html': e['files']['index.html'].replace(old, s['system_sha256']), 'system.json': mod['dump'](s)})
            e['files']['manifest.json'] = mod['manifest_of'](e['files'], s['system_sha256'])
            e['folder'] = e['folder'][:-16] + fsha(e['files']['manifest.json'])[:16]
        first = systems[0]
        want = {first['folder'] + '/' + n: fsha(text_) for n, text_ in first['files'].items()}
        for i, x in enumerate(d['scenes']['system']['command']):
            x['written'] = dict(want) if i in (0, 1, 4) else dict(want, **{first['folder'] + '/notes.txt': fsha('mine')})
            x['stdout'] = [line[:line.index('<out>/')] + '<out>/' + first['folder'] + '/index.html' for line in x['stdout']]
            x['stderr'] = [line if '<out>/' not in line else 'g2.py: error: <out>/' + first['folder'] + line[line.index(' already holds'):] for line in x['stderr']]
        if type(d.get('added')) is dict and 'system' in d['added'].get('scenes', {}):
            d['added'] = dict(d['added'], scenes=dict(d['added']['scenes'], system=v.sha(d['scenes']['system'])))
        return d

    def _other_question(self, d, v, cid, i, words):
        """Case `cid` and recorded system number i, built from its packs, re-made alike with other words in the question: the receipt of the run that asked, that
        run in the case and its copies, the two runs that answer it in the system's record.json, and system.json, the part files and the page written again from
        the forged record by the checks' own rules."""
        mod = check_module()
        row_ = pack(g2.EXHIBITS)['domains'][i - 6]

        def rehash(r):   # one run with its receipt and its chain hashed again
            prev = 'GENESIS'
            for k, e in enumerate(r['trace']):
                if e['operation'] == 'LOCAL_EFFECT':
                    e['data']['receipt']['sha256'] = v.sha({x: y for x, y in e['data']['receipt'].items() if x != 'sha256'})
                e.update(seq=k + 1, prev_sha256=prev)
                e['sha256'] = prev = v.sha({x: y for x, y in e.items() if x != 'sha256'})
            r['model_receipts'] = [e['data']['receipt'] for e in r['trace'] if e['operation'] == 'LOCAL_EFFECT']
            r['trace_root_sha256'] = prev
        c = [x for x in d['cases'] if x['id'] == cid][0]
        r = c['outcome']
        old = r['model_receipts'][0]['sha256']
        for e in r['trace']:
            if e['operation'] == 'LOCAL_EFFECT':
                e['data']['receipt']['ask']['question'] = words
        rehash(r)
        new = r['model_receipts'][0]['sha256']
        r['learning_record']['source_trace'] = r['trace_root_sha256']
        c['run']['runs'][0] = json.loads(json.dumps(r))
        c['four_views']['run'] = json.loads(json.dumps(r['trace']))
        c['derived_state']['historical_events'][0]['trace_root_sha256'] = r['trace_root_sha256']
        e = d['scenes']['system']['systems'][i]
        rec = json.loads(e['files']['record.json'])
        rec['runs'][0] = {k: x for k, x in json.loads(json.dumps(r)).items() if k not in ('learning', 'learning_record')}
        for name, j in (('runs', 1), ('no_runs', 0)):   # the yes and the no name the receipt they answer by its digest
            rec[name][j] = json.loads(json.dumps(rec[name][j]).replace(old, new).replace('ask-' + old[:12], 'ask-' + new[:12]))
            rehash(rec[name][j])
        s = mod['system_of'](row_['say'], [row_], row_, rec, d['action_handlers'], pack, v.sha)
        style = re.findall(r'<style>(.*?)</style>', e['files']['index.html'], re.S)[0]
        e['looks'] = {'runs': json.loads(json.dumps(mod['looks_of'](rec)))}
        e['files'].update({'record.json': mod['dump'](rec), 'system.json': mod['dump'](s), 'index.html': mod['page_of'](s, rec, style), 'workflow.json': mod['dump'](s['implementation']['workflow']),
                           'atoms.json': mod['dump'](s['implementation']['atoms']), 'scaffold.json': mod['dump'](s['implementation']['scaffold'])})

    def test_limit_the_words_of_a_question_of_case_70_or_71_are_held_by_no_check(self):
        # Confirming round, refuter 2, finding 1. A question's words reach a page from the receipt of the run that asked, and no check compares a receipt's question
        # with the method in the pack file. For the order system that run is the run of case 29, which the lab recorded before this version. Cases 70 and 71 are this
        # version's own: re-made end to end with other words (every digest made to fit), the record passes the eight rows that read it, and the forged page asks one
        # thing in its panel while its workflow table still carries the method's own question. Who is asked stays pinned (S126, S128). Owed to the next version:
        # every ask receipt held to its method in the pack files.
        data = recorded()
        if data is None:
            self.skipTest('results/actual_run_records.json is generated by tools/run_all.py')
        v = verifier()
        self.assertEqual(self._rows(data, v), [])
        for cid, i, name, words, own in (('71_no_plan_after_a_yes', 9, MINE[7], 'May we charge your card a second time?', 'ask customer: Did the parcel arrive? Then wait'),
                                         ('70_recorded_open', 8, MINE[6], 'May we keep your money and send nothing?', 'ask customer: May we send a replacement for the item that is out of stock? Then wait')):
            d = json.loads(json.dumps(data))
            self._other_question(d, v, cid, i, words)
            self.assertEqual(self._rows(self._sealed(d, v), v), [], cid)
            page = d['scenes']['system']['systems'][i]['files']['index.html']
            self.assertIn(f'<legend><b>Customer</b> is asked: {words}</legend>', page, cid)
            self.assertIn(own, page, cid)
            d = json.loads(json.dumps(data))   # who is asked is pinned: another party in the case's receipt, and the case's row refuses it
            [c for c in d['cases'] if c['id'] == cid][0]['outcome']['model_receipts'][0]['ask']['to'] = 'the desk'
            self.assertEqual(self._rows(d, v), [name], cid)

    def test_limit_record_json_is_held_as_what_it_parses_to_not_as_its_text(self):
        # Confirming round, refuter 2, finding 2. Of the eight recorded systems with a domain the checks read record.json as JSON: what it parses to is held (every
        # look and run, by S121 and S201), its text is compared with nothing. A key written twice, of which a parser keeps the last, or the same value written with
        # other spacing passes the eight rows; the manifest and the folder's name then carry the digest of that text. The two systems without a domain are compared
        # whole. What holds the text today is in this file: the builder writes each key once, and the record on disk is the builder's bytes. Owed to the next
        # version: record.json compared with its own dump for every system.
        data = recorded()
        if data is None:
            self.skipTest('results/actual_run_records.json is generated by tools/run_all.py')
        v, S = verifier(), lambda d: d['scenes']['system']['systems']
        one_writing = lambda text_: json.dumps(json.loads(text_), indent=2, ensure_ascii=False) + '\n'
        for s, e in zip(g2.demo(), S(data)):   # what the owed check would hold, held here: record.json is the one writing of what it parses to, as the builder writes it and as the record keeps it
            self.assertEqual((s['files']['record.json'], e['files']['record.json']), (one_writing(s['files']['record.json']),) * 2, s['asked'])
        d = json.loads(json.dumps(data))
        honest = S(d)[0]['files']['record.json']
        S(d)[0]['files']['record.json'] = '{\n  "plan": {"status": "EXECUTED_FOR_REAL", "note": "approved by the board; ran outside the local model"},' + honest[1:]
        self.assertEqual(json.loads(S(d)[0]['files']['record.json']), json.loads(honest))   # the parser keeps the last plan: what the checks read is the honest record
        self.assertEqual(self._rows(self._sealed(d, v), v), [])
        self.assertTrue(S(d)[0]['files']['record.json'].startswith('{\n  "plan": {"status": "EXECUTED_FOR_REAL"') and S(d)[0]['folder'] != S(data)[0]['folder'])   # the folder is named after the forged bytes
        d = json.loads(json.dumps(data))
        S(d)[1]['files']['record.json'] = json.dumps(json.loads(S(d)[1]['files']['record.json']), ensure_ascii=False)   # the same value on one line
        self.assertEqual(self._rows(self._sealed(d, v), v), [])
        for i in (4, 5):   # no domain: the checks make the draft's one look themselves and compare the text whole
            d = json.loads(json.dumps(data))
            S(d)[i]['files']['record.json'] = '{\n  "draft": {"status": "EXECUTED_FOR_REAL"},' + S(d)[i]['files']['record.json'][1:]
            self.assertEqual(self._rows(self._sealed(d, v), v), [MINE[1]], i)

    def test_limit_a_key_added_to_case_70_or_71_is_read_by_no_row(self):
        # Confirming round, refuter 2, finding 4 (a note). S126 and S128 compare what a case says beside its run by value. A key added to the case itself, to its
        # outcome and the run block's copy of that run, to its derived_state or to its four_views is read by no row of this version (the verifier says the same of
        # a key added to a run, for every case). A key added one level further in is refused. Owed to the next version: closed lists of keys for those four.
        data = recorded()
        if data is None:
            self.skipTest('results/actual_run_records.json is generated by tools/run_all.py')
        v, note = verifier(), {'note': 'approved by the board'}
        read_by_no_row = {'the case itself': lambda c: c.update(note), "its outcome and the run block's copy of that run": lambda c: (c['outcome'].update(note), c['run']['runs'][0].update(note)),
                          'its derived_state': lambda c: c['derived_state'].update(note), 'its four_views': lambda c: c['four_views'].update(note)}
        refused = {'its run block': lambda c: c['run'].update(note), 'a row of its world view': lambda c: c['four_views']['world'][0].update(note),
                   'a rule of its knowledge view': lambda c: c['four_views']['knowledge'][0].update(note), 'a stored fact': lambda c: list(c['derived_state']['facts'].values())[0].update(note),
                   'its budget': lambda c: c['derived_state']['budget_after'].update(note=1),
                   'the learning record of its run': lambda c: (c['outcome']['learning_record'].update(note), c['run']['runs'][0]['learning_record'].update(note))}
        for cid, name in (('70_recorded_open', MINE[6]), ('71_no_plan_after_a_yes', MINE[7])):
            for where, put in list(read_by_no_row.items()) + list(refused.items()):
                d = json.loads(json.dumps(data))
                put([c for c in d['cases'] if c['id'] == cid][0])
                self.assertEqual(self._rows(d, v), [] if where in read_by_no_row else [name], (cid, where))

    def test_limits_of_the_checks_taken_together_pass_all_nine_rows(self):
        # The three limits above in one record, and all nine rows of this version on it, the forgery row included (it reads the eight others on its forged copies of
        # the record it is handed, so it vouches for this one too). The base's own checks are not asked here: the add-on base pins what a version recorded only when
        # the next version is applied, and from then on its S202 refuses each of these records.
        data = recorded()
        if data is None:
            self.skipTest('results/actual_run_records.json is generated by tools/run_all.py')
        v, S, note = verifier(), lambda d: d['scenes']['system']['systems'], {'note': 'approved by the board'}
        d = json.loads(json.dumps(data))
        self._other_question(d, v, '71_no_plan_after_a_yes', 9, 'May we charge your card a second time?')
        self._other_question(d, v, '70_recorded_open', 8, 'May we keep your money and send nothing?')
        S(d)[0]['files']['record.json'] = '{\n  "plan": {"status": "EXECUTED_FOR_REAL"},' + S(d)[0]['files']['record.json'][1:]
        S(d)[1]['files']['record.json'] = json.dumps(json.loads(S(d)[1]['files']['record.json']), ensure_ascii=False)
        for c in d['cases']:
            if c['id'] in ('70_recorded_open', '71_no_plan_after_a_yes'):
                [x.update(note) for x in (c, c['outcome'], c['run']['runs'][0], c['derived_state'], c['four_views'])]
        self.assertEqual(self._rows(self._sealed(d, v), v, whole=True), [])

    # ---------------------------------------------------------------- what a mutation run of the builder left alive (confirming round, refuter 2, finding 3)
    # The run behind the four tests below, made when the confirming round was settled: in extensions/system.py every and/or swapped, every comparison turned to
    # its neighbour (== and !=, < and <=, > and >=, in and not in, is and is not), every not dropped, every if-expression swapped, every whole number plus one,
    # and ' ZZ ' put into the middle of every text that is no docstring. That is 1796 single mutations, each in a process of its own, first against the ten
    # recorded systems and then against this file (without the two tests that only read the checks). 1267 changed a recorded system, 322 failed a test, 3 ran
    # until they were stopped, and 204 lived. 173 of those now fail one of the four tests below (all but four of them change what a page, a system or a refusal
    # says for some pack; the four are words for a result no pack reaches, held there for a result changed by hand). The 31 left change nothing a pack can reach: the builder's words for a status no run on a page carries (PLAN_READY, 2) and for a look after a completed run
    # that would wait (2); the bound of the loop that follows the questions (3); two conditions that are equal in every state a verdict allows and the choice of the
    # look a first sentence reads (3); the default for an empty catalogue, for a dimension the budget lacks (the kernel refuses such a pack first) and for an
    # arrow that ends on no box (4); an answer that starts no run (2); an admission that was accepted and still names a blocker (1); the clause for a planned
    # step without its grant, which no plan that is ready has (9); U+00A0 as a letter, which the words never hold once they are cleaned (2); a parked receipt
    # on a path that completed (1); and two that this run's own operator makes without effect (the dash a folder name is stripped of, 2).

    def test_the_code_point_lists_are_held_entry_by_entry(self):
        # A code point taken off a list, or the bound of a range moved by one, changed which characters a page drops or where a word ends, and no test failed.
        # The builder's fixed lists, written here a second time as closed ranges, and every code point classed by both writings.
        spans = lambda pairs: {c for lo, hi in pairs for c in range(lo, hi + 1)}
        hidden = [(0x00, 0x1f), (0x7f, 0x9f), (0xad, 0xad), (0x34f, 0x34f), (0x61c, 0x61c), (0x115f, 0x1160), (0x17b4, 0x17b5), (0x180e, 0x180e), (0x200b, 0x200b), (0x200e, 0x200f),
                  (0x202a, 0x202e), (0x2060, 0x206f), (0x2800, 0x2800), (0x3164, 0x3164), (0xd800, 0xdfff), (0xfeff, 0xfeff), (0xfff9, 0xfffb), (0xffa0, 0xffa0), (0x1d173, 0x1d17a), (0xe0000, 0xe007f)]
        modifier = [(0x180b, 0x180f), (0x200c, 0x200d), (0xfe00, 0xfe0f), (0xe0100, 0xe01ef)]
        mark = [(0x00, 0x2f), (0x3a, 0x40), (0x5b, 0x60), (0x7b, 0x7f), (0xa1, 0xbf), (0xd7, 0xd7), (0xf7, 0xf7), (0x2000, 0x206f), (0x3000, 0x303f), (0xff00, 0xff0f)]
        spaces = [(0x09, 0x0d), (0x1c, 0x20), (0x85, 0x85), (0xa0, 0xa0), (0x1680, 0x1680), (0x2000, 0x200a), (0x2028, 0x2029), (0x202f, 0x202f), (0x205f, 0x205f), (0x3000, 0x3000)]
        unseen = {0xad, 0x34f, 0x61c, 0x115f, 0x1160, 0x17b4, 0x17b5, 0x180e, 0x200b, 0x200e, 0x200f, 0x2800, 0x3164, 0xfeff, 0xffa0}
        for name, test, want in (('hides or re-orders', G._hidden, hidden), ('only changes its neighbour', G._modifier, modifier), ('separates words', G._mark, mark)):
            self.assertEqual([hex(c) for c in sorted({c for c in range(0x110000) if test(c)} ^ spans(want))], [], name)   # every code point there is, classed alike by both writings
        self.assertEqual(([hex(c) for c in sorted(set(G._SPACES) ^ spans(spaces))], [hex(c) for c in sorted(set(G._UNSEEN) ^ unseen)]), ([], []))
        blank = spans(spaces)
        for lo, hi in hidden:   # what the lists do: the first and the last character of every range, in the words and in a string a page is given
            for c in (lo, hi):
                self.assertEqual(G._clean('a web' + chr(c) + 'site'), 'a web site' if c in blank else 'a website', hex(c))
                self.assertEqual(G._e('web' + chr(c) + 'site'), 'web' + chr(c) + 'site' if c in (0x09, 0x0a) else 'website', hex(c))   # on a page a tab and a line break stay; everything else that is hidden goes
        for lo, hi in spaces:
            for c in (lo, hi):
                self.assertEqual((G._clean('a' + chr(c) + 'b'), G._tokens('web' + chr(c) + 'site')), ('a b', {'web', 'site'}), hex(c))
        for lo, hi in mark:
            for c in (lo, hi):
                self.assertEqual(G._tokens('web' + chr(c) + 'site'), {'web', 'site'}, hex(c))
        for lo, hi in modifier:
            for c in (lo, hi):
                self.assertEqual((G._says_something(chr(c)), G._says_something(chr(0x8fba) + chr(c))), (False, True), hex(c))   # alone it says nothing; beside a letter the letter still counts
        lrm, alm, shy = chr(0x200e), chr(0x61c), chr(0xad)   # two direction marks (left-to-right, Arabic letter) and a soft hyphen
        s = g2.build('a web' + lrm + 'site for' + alm + ' my organ' + shy + 'isation')   # in the words: none arrives, and the domain is found
        self.assertEqual((s['asked'], s['verdict'], s['folder'][:30]), ('a website for my organisation', 'READY', 'a-website-for-my-organisation-'))
        named = build(world(['done'], methods=[m('mk', 'done')]), labels={'mk': 'Write' + lrm + ' the' + alm + ' site', 'done': 'the site' + shy + ' is written'})   # and in strings that come from a pack
        page = named['files']['index.html']
        self.assertEqual((re.findall(r'<text[^>]*>([^<]*)</text>', page), [c for c in (lrm, alm, shy) if c in page]), (['Write the site', 'the site is written'], []))

    def test_what_stands_in_the_way_is_said_reason_by_reason(self):
        # The builder's words for a reason and for what would unblock it lived when mutated: no test read a page with that reason. One page for every reason the kernel
        # or the builder can give, its row read whole (where, the reason with what the row adds to it, the recipe), and the rows of the kernel's gate held to the steps,
        # the slots and the budget they name.
        def way(s, page=None):
            rows = (page or s['files']['index.html']).split('<th>What would unblock it</th></tr>')[1].split('</table>')[0]
            return [tuple(html.unescape(x) for x in r) for r in re.findall(r'<tr><td>(.*?) <code>(.*?)</code></td><td>(.*?)</td><td>(.*?)</td></tr>', rows)]
        both, free, dear = [('done', [['a', 'b']])], {'compute': 0}, lambda money: {'compute': 8, 'money': money, 'attention': 0}
        grant = ('Mk-b', 'mk-b', 'A step has no permission to run', 'The grant for the step')
        slot = lambda where: (where.capitalize(), where, 'Nobody is free to do a step', 'A provider with a free slot')
        budget = lambda detail: ('Mk-a, mk-b', 'mk-a, mk-b', 'The budget does not cover the plan: ' + detail, 'A larger budget or a cheaper method')
        circle = lambda where: (where.capitalize(), where, 'The conditions depend on each other in a circle', 'Rules and methods that do not depend on each other in a circle')
        deep = ('P20', 'p20', 'The chain of conditions is deeper than the kernel follows: 20 levels', 'A shorter chain of conditions')
        route = lambda where, detail: (where.capitalize(), where, 'The steps that ran in the local model are not the steps of the plan on this page: ' + detail,
                                       'A domain in which one plan stays the cheapest before and after the answers, so that the page shows the steps that run')
        unreviewed = world(['done'], methods=[m('mk-a', 'a')])
        unreviewed['rules'] = [{'id': 'R-done', 'head': 'done', 'branches': [['a']], 'approved': False}]
        chain = lambda *more: world(['p0'], methods=[m(f's{i}', f'p{i}', cost=free, req=[f'p{i + 1}']) for i in range(21)] + [m('s21', 'p21', cost=free)] + list(more))   # 22 conditions in a row: the kernel stops at p20, which rests on p21
        ask = m('ask-payer', 'paid', 'ask', ASK, ask_to='payer')
        packed = [('G', [['packed', 'paid']])]
        blocked = {   # no plan: the kernel's own reason, the condition or the steps its trace names for it, and the recipe
            'a step without its grant': (world(['done'], both, [m('mk-a', 'a'), m('mk-b', 'b', grant='other')]), [grant]),
            'one provider with exactly as many slots as steps, another with none': (world(['done'], [('done', [['a', 'b', 'c']])], [m('mk-a', 'a'), m('mk-b', 'b'), m('mk-c', 'c', provider='other')],
                                                                                          providers={'prov': 2, 'other': 0}), [slot('mk-c')]),
            'a provider no pack declares': (world(['done'], both, [m('mk-a', 'a'), m('mk-b', 'b', provider='ghost')]), [slot('mk-b')]),
            'over the budget in one dimension, exactly at it in another': (world(['done'], both, [m('mk-a', 'a', cost=dear(5)), m('mk-b', 'b', cost=dear(5))]), [budget('compute: needs 16, has 10')]),
            'over the budget in two dimensions': (world(['done'], both, [m('mk-a', 'a', cost=dear(6)), m('mk-b', 'b', cost=dear(6))]), [budget('compute: needs 16, has 10; money: needs 12, has 10')]),
            'no grant and over the budget': (world(['done'], both, [m('mk-a', 'a', cost=dear(0)), m('mk-b', 'b', grant='other', cost=dear(0))]), [grant, budget('compute: needs 16, has 10')]),
            'nobody wrote down what the goal means': (world(['done']), [('Done', 'done', 'Nobody has written down what this goal means', 'A reviewed rule that says what the goal means')]),
            'a rule nobody reviewed': (unreviewed, [('Done', 'done', 'What this goal means is drafted but not reviewed', 'A reviewer approving the drafted rule')]),
            'a circle of methods': (world(['a'], methods=[m('ma', 'a', req=['b']), m('mb', 'b', req=['a'])]), [circle('a')]),
            'a circle through a rule': (world(['G'], [('G', [['x']])], [m('mx', 'x', req=['G'])]), [circle('G')]),
            'a decision': (world(['done'], methods=[m('ship', 'done', req=['export_ok'])], evidence=[row('export_ok', 'FALSE', final=True, source='policy/export-control')]),
                           [('Export_ok', 'export_ok', 'A decision stands against it, and no method may overturn that', 'Nothing here: the decision is final; another route to the goal would have to exist')]),
            'a chain deeper than the kernel follows': (chain(), [deep]),
            'the same chain, and a method nobody reviewed that would close a circle': (chain(m('back', 'p21', cost=free, req=['p20'], approved=False)), [deep]),
            'the same chain, and a reviewed method that closes the circle': (chain(m('back', 'p21', cost=free, req=['p20'])), [circle('p20')])}
        for name, (w, rows) in blocked.items():
            s = build(w)
            self.assertEqual((s['verdict'], way(s)), ('BLOCKED', rows), name)
        self.assertEqual([b['detail'] for b in build(blocked['no grant and over the budget'][0])['blocked_at']], [None, 'compute: needs 16, has 10'])   # the row of the grant carries no word about the budget
        zero = [m('u1', 'u', cost=free), m('u2', 'u', cost=free)]
        found = {   # a plan that does not get there: the builder's own rows
            'another route, one step in, one step out': (world(['G'], packed, [ask, m('pack-a', 'packed'), m('pack-b', 'packed', 'compile_candidate', req=['paid'], constructor='none')]),
                                                           [route('pack-a, pack-b', 'chosen outside the plan: pack-a; planned and not run: pack-b')]),
            'another route, two steps in, two steps out': (world(['G'], packed, [ask, m('p1', 'pre'), m('p2', 'packed', req=['pre']), m('q1', 'pre2', req=['paid']), m('q2', 'packed', req=['pre2'])]),
                                                             [route('p1, p2, q1, q2', 'chosen outside the plan: p1, p2; planned and not run: q1, q2')]),
            'another route that stops at its first step': (world(['G'], packed, [ask, m('pack-a', 'packed', 'compile_candidate', constructor='none'), m('pack-b', 'packed', req=['paid'])]),
                                                             [route('pack-a', 'chosen outside the plan: pack-a; planned and not run: nothing'),
                                                              ('Pack-a', 'pack-a', 'A step could not run in the local model, and the run stopped there: Handler refused: No declared constructor',
                                                               "What the stopped step needs; the reason is in the kernel's own words")]),
            'a step planned twice for one fact, made true before the question': (world(['done'], [('done', [['y', 'z']])], zero + [m('y', 'y', req=['u']), m('ask', 'approved', 'ask', ASK, ask_to='customer', req=['y']),
                                                                                                                             m('z', 'z', req=['approved', 'u'])]),
                                                                                   [route('u2', 'chosen outside the plan: nothing; planned and not run: u2')]),
            'another route with a step that is already true at its turn': (world(['G'], [('G', [['packed', 'other', 'paid']])], [ask, m('p1', 'pre', cost=free), m('p1b', 'pre', cost=free), m('p2', 'packed', req=['pre']),
                                                                                                                             m('p3', 'other', req=['pre']), m('q2', 'packed', req=['paid']), m('q3', 'other', req=['paid'])]),
                                                                             [route('p2, p1b, q2', 'chosen outside the plan: p2, p1b; planned and not run: q2')])}
        for name, (w, rows) in found.items():
            s = build(w)
            self.assertEqual((s['verdict'], way(s)), ('NOT_READY', rows), name)
        keep = G.validate_workflow   # the builder's two findings about the generated workflow, shown with a validator and a checklist that find a fault
        G.validate_workflow = lambda wf: ['step x comes before its prerequisite y', 'step z has no check']
        try:
            s = g2.build(WEBSITE)
        finally:
            G.validate_workflow = keep
        malformed = ('The workflow generated from the plan is not well formed', 'A generator that writes this plan as a well-formed workflow')
        self.assertEqual(way(s), [('Step x comes before its prerequisite y', 'step x comes before its prerequisite y') + malformed, ('Step z has no check', 'step z has no check') + malformed])
        self.assertIn('workflow problems: step x comes before its prerequisite y; step z has no check.</p>', s['files']['index.html'])
        keep = G.workflow_facts
        G.workflow_facts = lambda wf: [dict(r, truth='FALSE') if r['predicate'] == 'has_trigger' else r for r in keep(wf)]
        try:
            s = g2.build(WEBSITE)
        finally:
            G.workflow_facts = keep
        self.assertEqual(way(s), [('Has_trigger', 'has_trigger', 'The workflow generated from the plan lacks a part the standard asks for: no reviewed way exists to make a needed condition true',
                                   'A workflow that carries the missing part')])
        goal = pack('30_build_goal')['goals'][0]   # a step whose effect does not hold afterwards (the lab's own constructor packs)
        s = G.build_system('build it', [{'id': 'build', 'title': 'Builder', 'goal': goal, 'say': 'build it', 'words': ['build'], 'packs': ['30_build_goal', '31_build_theory', '32_builder_components']}], pack)
        self.assertEqual(way(s), [('Construct-enquiry-candidate@1', 'construct-enquiry-candidate@1', 'A step ran in the local model and what it should make true does not hold afterwards',
                                   'A method whose step stores its effect as evidence'),
                                  ('Capability_candidate_created', 'capability_candidate_created', 'Every step ran in the local model, and afterwards the goal still does not hold: the kernel would plan the same steps again',
                                   'A newer observation of the goal, or rules and facts that agree with each other')])
        self.assertIn('<g class="stop"><title>construct-enquiry-candidate@1 makes capability_candidate_created</title>', s['files']['index.html'])   # drawn as the step where it goes wrong
        lone = world(['paid'], methods=[m('ask-payer', 'paid', 'ask', ASK, ask_to='payer')])   # a run that parks on a question nobody can answer (the kind lost its books)
        s = with_kind('ask', lambda old: {k: x for k, x in old.items() if k != 'settle'}, lambda: build(lone))
        self.assertEqual(way(s), [('Ask-payer', 'ask-payer', 'The run in the local model still waits after every question was answered', 'A review of the domain: the model run found no question left to answer')])
        self.assertIn('<summary>A run in the local model: the run still waits</summary>', s['files']['index.html'])
        nothing = build(world(['done']))   # a reason the builder has no words for is not reached with this kernel: the page gives the reason as it is and a recipe that fits any
        page = G._page(dict(nothing, blocked_at=[{'reason': 'A_NEW_REASON', 'at': ['done'], 'detail': None}]), json.loads(nothing['files']['record.json']))
        self.assertEqual((way(nothing, page), '<p class="lead">Cannot start: A_NEW_REASON (done).</p>' in page), ([('Done', 'done', 'A_NEW_REASON', 'A reviewed change to the packs')], True))

    def test_a_refusal_of_the_builder_says_what_was_refused(self):
        # The words of the builder's refusals lived when mutated: the tests asked only for a ValueError. Each refusal, word for word where the words are the builder's
        # own (what a loader or the kernel adds after the colon is theirs).
        rows = g2.catalogue()
        ok = world(['a'], methods=[m('ma', 'a')])

        def no_standard(n):
            if n == 'w':
                return copy.deepcopy(ok)
            raise FileNotFoundError(n)
        entry = {'id': 'w', 'title': 'W', 'goal': 'a', 'say': 'ship it', 'words': ['ship'], 'packs': ['w']}
        said = {'The catalogue is a list of domains': lambda: G.build_system('a site', {'website': rows[0]}, pack),
                'A catalogue row needs an id, a title, a goal, an example of what a person would say, words and packs (and labels in plain text)': lambda: G.build_system('a site', ['website'], pack),
                'Two catalogue rows share the id website': lambda: G.build_system('a site', rows + [rows[0]], pack),
                'Say the goal in words': lambda: G.build_system(None, rows, pack),
                'Unknown domain: pick one from the catalogue': lambda: G.build_system('a site', rows, pack, 'a-domain-nobody-reviewed'),
                'The domain order must leave exactly one standing goal, another_goal': lambda: G.build_system('ship it', [dict(rows[1], goal='another_goal')], pack),
                'The domain w must leave exactly one standing goal, a': lambda: build(world(['a', 'b'], methods=[m('ma', 'a'), m('mb', 'b')])),
                "The domain order does not load: 'w'": lambda: G.build_system('ship it', [dict(rows[1], packs=['w'])], lambda n: {}[n]),   # what the loader raised, in its own words
                'The domain w does not load: 60_standard_goal': lambda: G.build_system('ship it', [entry], no_standard),
                'The domain order does not load: RecursionError': lambda: G.build_system('ship it', [dict(rows[1], packs=['w'])], lambda n: json.loads('[' * 100000))}   # a pack too deep to read: the name of the error, not its text
        for words, attempt in said.items():
            with self.assertRaises(ValueError) as stop:
                attempt()
            self.assertEqual(str(stop.exception), words)
        with self.assertRaises(ValueError) as stop:
            G.build_system('?! ' + chr(0x2014), rows, pack)
        self.assertEqual(str(stop.exception), 'Say the goal in words')   # words that say nothing are refused like words that are no text
        with self.assertRaises(ValueError) as stop:
            G.build_system('ship it', [dict(rows[1], packs=['no_such_pack'])], pack)
        self.assertTrue(str(stop.exception).startswith('The domain order does not load: ') and 'no_such_pack' in str(stop.exception), str(stop.exception))
        keep = G._built   # packs that load and are too deep to build are not reached with a pack file here: the refusal is shown with a build that ends in Python's error
        def too_deep(*given):
            raise RecursionError('maximum recursion depth exceeded')
        G._built = too_deep
        try:
            with self.assertRaises(ValueError) as stop:
                build(ok)
        finally:
            G._built = keep
        self.assertEqual(str(stop.exception), 'The domain w is deeper than this lab follows')

    def test_what_the_confirming_mutation_run_changed_on_a_page_unseen_is_held(self):
        # Sentences, marks of the picture, cuts of a long name and the record of the code behind a kind: each line below fails under a single mutation of the builder
        # that every test let through before.
        ask = m('ask-payer', 'paid', 'ask', ASK, ask_to='payer')
        packed = [('G', [['packed', 'paid']])]
        yes_panel = lambda s: re.search(r'<div class="panel y">(.*?)</div>', s['files']['index.html']).group(1)
        two_out = build(world(['G'], packed, [ask, m('p1', 'pre'), m('p2', 'packed', req=['pre']), m('q1', 'pre2', req=['paid']), m('q2', 'packed', req=['pre2'])]))   # two steps chosen outside the plan, two planned steps never run
        self.assertEqual(lead(two_out), 'A plan was found, but the local model took another route, after payer said yes: the kernel chose p1, p2, which are no steps of the plan on this page; '
                                        'q1, q2 are steps of that plan and never ran.')
        twin = build(world(['done'], [('done', [['y', 'z']])], [m('u1', 'u', cost={'compute': 0}), m('u2', 'u', cost={'compute': 0}), m('y', 'y', req=['u']),
                                                               m('ask', 'approved', 'ask', ASK, ask_to='customer', req=['y']), m('z', 'z', req=['approved', 'u'])]))
        self.assertEqual((twin['verdict'], twin['plan']['actions'], [[x['method'] for x in r['receipts']] for r in twin['model_run']['path']], twin['model_run']['goal_held']),
                         ('NOT_READY', ['u1', 'y', 'ask', 'u2', 'z'], [['u1', 'y', 'ask'], ['z']], True))   # nothing outside the plan ran: the kernel planned a second step for a fact the first had made true by then, and dropped it after the answer
        self.assertEqual(lead(twin), 'A plan was found, but the local model took another route, after customer said yes: u2 is a step of that plan and never ran.')
        self.assertIn('<g class="later"><title>u2 makes u</title>', twin['files']['index.html'])
        gone = build(world(['G'], packed, [ask, m('pack-a', 'packed'), m('pack-b', 'packed', 'compile_candidate', req=['paid'], constructor='none')], [row('G', 'FALSE')]))   # another route, and the goal does not hold afterwards
        self.assertEqual(([b['reason'] for b in gone['blocked_at']], yes_panel(gone)),
                         (['ROUTE_CHANGED', 'GOAL_NOT_HELD'], '<p><b>The kernel takes another route than the plan on this page, and afterwards the goal still does not hold.</b> Ran in the local model: pack-a.</p>'))
        three = build(world(['done'], [('done', [['x', 'y', 'z']])], [m('ask', 'approved', 'ask', ASK, ask_to='customer')] + [m(f'u{i}', 'u', cost={'compute': 0}, req=['approved']) for i in (1, 2, 3)]
                            + [m(n, n, req=['u']) for n in 'xyz']))   # two steps already true at their turn after one answer
        self.assertEqual(yes_panel(three), '<p><b>The plan runs through in the local model.</b> Ran in the local model: u1, x, y, z. Already true at their turn and skipped: u2, u3.</p>')
        early = build(world(['shipped'], methods=[m('cand', 'c', 'compile_candidate', constructor='none'), m('ask-ok', 'ok', 'ask', ASK, ask_to='customer', req=['c']), m('ship', 'shipped', req=['ok'])]))   # a question the run never reached
        for words in ('customer would be asked whether ok (not reached in the local model)', '<g class="ask later"><title>ask-ok asks customer whether ok</title>'):
            self.assertIn(words, early['files']['index.html'])
        two, five, six = build(self._asks(2)), build(self._asks(5, [m('cand', 'c', 'compile_candidate', constructor='none')])), build(self._asks(6))
        self.assertEqual(re.findall(r'<tr><td>\d</td><td>([^<]*)</td><td>[^<]*</td><td>[^<]*</td><td>[^<]*</td></tr>', two['files']['index.html']),
                         ['A question is out and the run waits for the answer', 'After party0 said yes: a question is out and the run waits for the answer',
                          'After party1 said yes: the plan ran through in the local model'])   # each run of the table names the party whose yes it followed
        self.assertIn('The plan executed against a model of the world, with 5 questions answered yes before it ended.', five['files']['index.html'])
        page = six['files']['index.html']
        for words in ('<p class="hint">Asked by the step ask-2, only after party0, party1 said yes. The answer must come from party2 and present the receipt of this question.</p>',
                      '</fieldset><p class="hint">Asked by the step ask-3, only after party0, party1, party2 said yes. The answer must come from party3 and present the receipt of this question.</p>'
                      '<p class="hint">The plan asks 6 questions. The first 4 are shown above with both answers; these follow, each only after every question before it was answered yes:</p>'
                      '<ul><li><b>Party4</b> is asked: May step 4 go ahead?</li><li><b>Party5</b> is asked: May step 5 go ahead?</li></ul><h2>The details</h2>'):
            self.assertIn(words, page)
        texts = lambda s: re.findall(r'<text[^>]*>([^<]*)</text>', s['files']['index.html'])   # the lines of a box: the name on 23 characters, what it makes or whom it asks on 27
        party = lambda name: build(world(['done'], methods=[m('ask', 'approved', 'ask', ASK, ask_to=name), m('mk', 'done', req=['approved'])]))
        self.assertEqual((texts(party('the head of the office'))[1], texts(party('the head of the offices'))[1]), ('asks the head of the office', 'asks the head of the off...'))
        named = lambda **labels: texts(build(world(['done'], methods=[m('mk', 'done')]), labels=labels))
        self.assertEqual((named(mk='Plan and write the pages now'), named(done='the whole of the websites is ok and more')),
                         (['Plan and write the', 'pages now', 'done'], ['mk', 'the whole of the websites', 'is ok and more']))
        self.assertEqual((G._wrap('abc def ghijk', 10, 1), G._wrap('ab cd efg hijkl', 11, 1), G._cap('a' + chr(0xe9)), G._cap(chr(0xe9) + 'a')), (['abc def...'], ['ab cd...'], 'A' + chr(0xe9), chr(0xe9) + 'a'))   # three dots fit exactly; one word goes at a time; a capital for an ASCII letter, whatever follows it
        fan = build(world(['done'], [('done', [[f'e{i}' for i in range(1, 7)]])], [m('first', 'a'), m('second', 'b', req=['a']), m('third', 'c', req=['b'])] + [m(f'x{i}', f'e{i}', req=['a', 'c']) for i in range(1, 7)],
                          budget={'compute': 30}))
        long = [pts for pts in picture(fan['files']['index.html'])[1] if len(pts) == 5]   # six arrows that skip a column share five lanes: the sixth takes the first lane again
        self.assertEqual((fan['verdict'], [pts[1][0] for pts in long], crossings(fan['files']['index.html'])), ('READY', [187.0, 191.0, 195.0, 199.0, 203.0, 187.0], []))
        waits = build(world(['done'], methods=[m('ask', 'approved', 'ask', ASK, ask_to='customer'), m('mk', 'done', req=['approved'])]))
        again = {'status': 'WAITING', 'work_state': 'waiting', 'receipts': [], 'skipped': [], 'pending': ['mk']}   # a run that waits after an answer without a new question, and a run that ends with nothing to do and the goal not held, are not reached with packs: the sentences are held for a result changed by hand
        ended = {'status': 'SUPPORTED_BY_EVIDENCE', 'work_state': 'completed', 'receipts': [], 'skipped': [], 'pending': []}
        self.assertEqual((G._outcome(waits, again, None, True), G._outcome(waits, again, None, False), G._outcome(waits, ended, False, True)),
                         ('<p><b>The run goes on and waits again.</b> Not run: mk.</p>', '<p><b>Another route is taken and waits again.</b> Not run: mk.</p>',
                          '<p><b>No step is left to run, and the goal still does not hold.</b></p>'))

        class Held:   # a handler that is an object: the code on the record is that of its __call__, in this file
            def __call__(self, state, mm, mid, deps):
                return {}
        made = {}
        exec('def run(state, mm, mid, deps):\n    return {}\n', made)   # code made from a text has no file to digest, and the record says so
        self.assertEqual((G._code(Held()), G._code(made['run'])),
                         ({'function': '__call__', 'file': 'tests/test_system.py', 'sha256': file_sha('tests/test_system.py')}, {'function': 'run', 'file': '<string>', 'sha256': None}))

    def test_the_readme_names_the_tests_that_hold_what_no_check_holds(self):
        # Where this version's passage says that a unit test alone holds a claim, or pins a limit, it names the test. Every name it gives is a test of this file, and
        # every limit pinned above is named there.
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        passage = readme[readme.index('0.14.0 (Core Algorithm program, 2026-11-14; the kernel is unchanged) adds the page builder'):]
        passage = passage[:passage.index('were not put through such a run.')]
        named = re.findall(r'`(test_[a-z0-9_]+)`', passage)
        pinned = sorted(n for n in dir(self) if n.startswith('test_limit'))
        self.assertEqual(([n for n in named if not callable(getattr(self, n, None))], [n for n in pinned if n not in named], len(pinned)), ([], [], 7))


if __name__ == '__main__':
    unittest.main()
