"""Independent checks of the page builder: the ten systems it recorded (the record's scenes.system block), the recorded
runs of its command, and cases 70 and 71. Reads the record and the pack files only; never imports the lab's code and never
runs the kernel or the builder.

How a recorded system is held. Every look and run of the kernel behind a page is in its record.json, whole, and once more
under `looks`, where the verifier's S201 holds each to its trace and its packs like any other run (by the rule of S42).
Here each is read again by this file's own rules (agrees). Everything else is WORKED OUT AGAIN from those results and the
pack files, by this file's own second writing of the builder's rules, and compared whole:
  system.json   the choice of the domain, the code recorded behind the kinds, the digests of the packs, the verdict, the
                rows that say what stands in the way, the generated workflow with its atoms and its scaffold (from the
                first look and the books the packs leave), the standard's checklist and verdict, what the run in the
                local model did and both answers to the question: one text, compared byte for byte
  index.html    the page, rendered here from that system and the first look's chain: one text, compared byte for byte,
                so nothing can be put into a page, taken out of it, wrapped, commented out or renamed
  record.json   of a system without a domain: the draft, the four rows of the kernel's look at it, their hashes and the
                whole result, made here from the words (it is the one look that ran on no scenario file)
A state this file has no words for (another route, several questions, a plan the gate turned away, a circle) reads as a
failure. Cases 70 and 71 are held beside their runs too: their scope, run block, world and knowledge views and rule ids
against their pack files, and what their run says beside its trace against this file's own values. Not held: what a
look or run of a recorded system says beside its trace (needs, proof lines, the branch, the truth of the goal,
candidates): record.json keeps it as the kernel returned it, and no other file and no page carries it. The digests inside
the record show that it is whole, not who wrote it, and a look or run that is no recorded case's is compared with its own
trace, not run again. S127 shows the claims fail on forged records, each forgery refused by the row it is listed for,
most of them with every digest, manifest, folder name and the command's recorded runs made to fit again, and the hardest
with system.json, the three part files and the page written again from the forged results by this file's own rules.

The module imports hashlib, html, json and re and nothing of the lab; checks() never raises: a record it cannot read is
nine failed rows."""
import hashlib
import html as _html
import json
import re

KINDS = ['ask', 'compile_candidate', 'emit_artifact', 'simulate_fact']
HOOKS = {'ask': {'check': '_check', 'plan': '_plan', 'run': 'ask', 'settle': '_settle'}, 'compile_candidate': {'run': 'compile_candidate'},
         'emit_artifact': {'run': 'emit_artifact'}, 'simulate_fact': {'run': '_simulate_fact'}}   # every function a State calls for each kind, by the name of its code
CATALOGUE, EXHIBITS, STANDARD = '171_domain_catalogue', '172_domain_exhibits', ['60_standard_goal', '61_standard_theory']
NEWS, TIE = 'a weekly newsletter for my donors', 'order a website'   # the two demo asks that build nothing: no shared word, and a tie
VERDICTS = ['READY', 'WAITING', 'READY', 'READY', 'NO_DOMAIN', 'NO_DOMAIN', 'BLOCKED', 'NOT_READY', 'NOT_READY', 'NOT_READY']
WORDS = {'READY': 'Ready', 'WAITING': 'Waiting on an answer', 'NOT_READY': 'Plan found, not ready', 'BLOCKED': 'No plan yet', 'NO_DOMAIN': 'Not built: no domain chosen'}
SAID = {'PLAN_READY': 'a plan is ready', 'LOCAL_MODEL_EFFECTS_RECORDED': 'the plan ran through in the local model', 'SUPPORTED_BY_EVIDENCE': 'the facts already support it',
        'WAITING': 'a question is out and the run waits for the answer', 'STEP_STOPPED': 'a step could not run in the local model, and the run stopped there',
        'REFUSED': 'a decision stands against it, and no method may overturn that', 'SEMANTICS_UNAPPROVED': 'what this goal means is drafted but not reviewed',
        'EVIDENCE_CONFLICT': 'the facts contradict each other', 'QUERY_EVIDENCE': 'a needed fact is unknown and nothing may ask for it',
        'METHOD_ABSENT': 'no reviewed way exists to make a needed condition true',
        'GOAL_NOT_HELD': 'every step ran in the local model, and afterwards the goal still does not hold'}   # this file's plain words for what the kernel says, on the pages on record
UNBLOCK = {'METHOD_ABSENT': 'a reviewed method that makes this condition true', 'QUERY_EVIDENCE': 'a verified fact for this condition, or a reviewed method that may ask for it',
           'EVIDENCE_CONFLICT': 'someone settling which fact is right: the stored row, or the conditions that say otherwise',
           'STEP_STOPPED': "what the stopped step needs; the reason is in the kernel's own words",
           'GOAL_NOT_HELD': 'a newer observation of the goal, or rules and facts that agree with each other'}
AFTER = {'PLAN_READY': 'the kernel would plan the same steps again', 'WAITING': 'the kernel would wait on a question again'}
TO_WRITE = ['What done means: the conditions that must be true, as one or more alternatives.',
            'What is true today: each condition as TRUE or FALSE, or left out when nobody knows. Not the goal itself: the kernel reads the goal from its conditions.',
            'The ways to make each condition true: one method per condition, with what it needs first. No method may make the goal itself.',
            'Who may run each method: a grant and a provider per method. Anything that needs a person is an ask, with the person named.',
            'What it costs: attention, money and compute per method, and the budget they must fit.',
            'A reviewer approves the rules. Until then the kernel plans nothing from them.']   # what a page without a domain says someone has to write down
INVARIANTS = ['unknown is neither true nor false; a failed check is not evidence of false', 'no action without an eligible provider, a scoped grant and available budget',
              'a local receipt is never proof of an external effect', 'nothing here promotes itself; registration needs an external approval path']
CHECKLIST = [('has_trigger', 'the workflow says what starts it', lambda w: bool((w.get('trigger') or {}).get('kind'))),
             ('every_step_has_check', 'every step carries a check of its own', lambda w: bool(w.get('steps')) and all(x.get('verify') for x in w['steps'])),
             ('has_overall_verify', 'the workflow says how the whole is verified', lambda w: bool(w.get('verify')))]   # the standard's three checks, read here off the written workflow
TAGS = {'html', 'head', 'meta', 'title', 'style', 'body', 'main', 'p', 'span', 'h1', 'h2', 'div', 'svg', 'path', 'polygon', 'g', 'rect', 'text', 'details', 'summary', 'table', 'tr', 'th',
        'td', 'code', 'pre', 'ul', 'ol', 'li', 'a', 'b', 'fieldset', 'legend', 'input', 'label', 'footer'}
ATTRS = {'lang', 'charset', 'name', 'content', 'class', 'viewBox', 'width', 'height', 'role', 'aria-label', 'd', 'points', 'x', 'y', 'rx', 'type', 'id', 'checked', 'for', 'href', 'colspan'}
BUILT_FILES = ['index.html', 'system.json', 'workflow.json', 'atoms.json', 'scaffold.json', 'record.json', 'manifest.json']
DRAFT_FILES = ['index.html', 'system.json', 'draft-pack.json', 'record.json', 'manifest.json']
RESULT_KEYS = {'goal', 'scope', 'goal_truth_before', 'work_state', 'actions', 'needs', 'cost', 'proof', 'model_receipts', 'candidates', 'selected_branch', 'stop_reasons', 'provenance', 'status',
               'pareto_options', 'pending', 'waits', 'goal_truth_after', 'skipped', 'stopped', 'trace', 'trace_root_sha256', 'claim'}   # every key a result of the kernel on record carries
STYLE_SHA256 = '383c01028598b907ce47cdae0d8c7f80c4f1bf214176250040f560e728013ccc'   # the one style sheet every page carries: another one is another page
CLAIM = 'LOCAL_REFERENCE_ONLY; never external success or current J2 implementation'   # the kernel's sentence, word for word
UNANSWERED = ("The run waits. Nothing after the question has run. Looking again asks nothing and costs nothing, and a way that costs less in this domain's "
              'order of preference is still taken.')   # what a page says under a question nobody has answered yet
NEW_DOMAIN = ('The draft is filled in and authored as packs, recorded as a case, and sent through the loop that tests every version. The catalogue is a reviewed pack too: '
              'the row for the new domain is an edit to that pack, reviewed like the packs it names. Once that version is promoted, the same words build a system.')
ASK, SHIP, RECEIPT = 'ask-customer-approval@1', 'ship-replacement@1', 'ask-customer-receipt@1'
# What the runs of cases 70 and 71 say beside their trace (needs, proof lines, the branch): this file's own values, which no other check reads
CASE70_SAYS = (['replacement_delivered', 'customer_approved'], ['order_complete ⇐ R-ORDER@1: alternative 2', 'ship-replacement@1 would establish replacement_delivered',
                                                              'substitute_stock observed TRUE (fixture/reviewed)', 'ask-customer-approval@1 would establish customer_approved'], 'R-ORDER@1/OR2')
CASE71_SAYS = (['receipt_confirmed'], ['order_closed ⇐ R-CLOSE@1: alternative 2', 'ask-customer-receipt@1 would establish receipt_confirmed'], 'R-CLOSE@1/OR2')
# What the ten systems on record say, system by system (a system without a domain says nothing here): the steps that ran in each run of the yes path, and the rows that
# say what stands in the way. A run that is no recorded case's is compared with its own trace, not run again: these two tables hold what such a run may say on a page.
RAN = [[['plan-site@1', 'write-content@1', 'build-pages@1', 'check-site@1']], [[ASK], [SHIP]], [['store-enquiry@1', 'readback-enquiry@1', 'check-privacy@1']], [['add-step-checks@1']], None, None,
       [], [['validate-field@1', 'store-component@1', 'read-component@1']], [[ASK], [SHIP]], [[RECEIPT], []]]
WAY = [[], [], [], [], None, None,
       [{'reason': 'METHOD_ABSENT', 'at': ['original_stock'], 'detail': None}, {'reason': 'QUERY_EVIDENCE', 'at': ['customer_approved'], 'detail': None}],
       [{'reason': 'STEP_STOPPED', 'at': ['construct-enquiry-candidate@1'], 'detail': 'Handler refused: No declared constructor'}],
       [{'reason': 'GOAL_NOT_HELD', 'at': ['order_complete'], 'detail': 'EVIDENCE_CONFLICT'}],   # a yes that ships and still does not get there is not waiting
       [{'reason': 'QUERY_EVIDENCE', 'at': ['refund_recorded'], 'detail': None}, {'reason': 'EVIDENCE_CONFLICT', 'at': ['order_closed'], 'detail': None}]]   # a yes after which the kernel has no plan is not waiting either
NAMES = ['S120_systems_whole_on_the_record', 'S121_every_look_and_run_behind_a_page_is_on_the_record', 'S122_systems_and_verdicts_follow_from_the_kernel_results',
         'S123_pages_are_what_this_file_renders_and_run_nothing', 'S124_no_guess_and_every_domain_a_recorded_case',
         'S125_the_command_writes_the_recorded_bytes_and_refuses_in_one_line', 'S126_case_70_waits_and_its_yes_does_not_get_there',
         'S128_case_71_waits_and_after_its_yes_the_page_names_the_reason_the_kernel_names']
FORGERIES = 'S127_system_claims_fail_on_forged_records'
FORGED = 295   # the number of forgeries below, as the README quotes it: a forgery added or dropped without this number fails S127

fsha = lambda text: hashlib.sha256(text.encode('utf-8')).hexdigest()
dump = lambda value: json.dumps(value, indent=2, ensure_ascii=False) + '\n'
canon = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
held = lambda look: bool(look) and look['status'] == 'PLAN_READY' and not look['actions']   # the kernel's dry look finds the goal held: a plan with nothing to do
short = lambda text, n: text if len(text) <= n else text[:n - 3] + '...'
esc = lambda x: _html.escape(str(x), quote=True)
cap = lambda t: (t[:1].upper() if t[:1].isascii() else t[:1]) + t[1:]
words_of = lambda t: {w for w in ''.join(ch.lower() if ch.isalnum() else ' ' for ch in t).split() if len(w) > 2}   # the recorded asks are plain ASCII words


class NoWords(Exception):
    """A state this file has no words for: no system on record is in it."""


def say(status):   # this file's plain words for a status or a reason of the kernel
    if status not in SAID:
        raise NoWords(status)
    return SAID[status]


def unblock(reason):   # this file's words for what would unblock a row
    if reason not in UNBLOCK:
        raise NoWords(reason)
    return UNBLOCK[reason]


def slug(text):   # the folder's name before the digest: the ASCII letters and digits of the words, lowered, everything else one dash, forty characters
    out = '-'.join(part for part in ''.join(ch.lower() if ch.isascii() and ch.isalnum() else '-' for ch in text).split('-') if part)
    return out[:40].strip('-') or 'goal'


def brief(r):   # what a system may say about one look or run of the kernel: what its hash chain carries
    return {'status': r['status'], 'work_state': r['work_state'], 'actions': r['actions'], 'pending': r.get('pending', []), 'skipped': r.get('skipped', []), 'cost': r.get('cost'),
            'stop_reasons': r.get('stop_reasons', []), 'stopped': r.get('stopped'), 'trace_root_sha256': r['trace_root_sha256'],
            'receipts': [{'method': x['method'], 'action': x['action'], 'status': x['status'], 'sha256': x['sha256'], 'ask': x.get('ask')} for x in r['model_receipts']]}


def looks_of(rec):   # the looks and runs of a built system's record.json, in the builder's fixed order
    return [rec['plan']] + rec['runs'] + rec['no_runs'] + [x for x in rec['no_after'] if x] + [x for x in (rec['after'], rec['standard']) if x]


def manifest_of(files, system_sha256):   # the manifest a folder carries: the digest of every other file, and the system's
    return json.dumps({'schema': 'core-algorithm/system-manifest/1', 'system_sha256': system_sha256, 'files': {n: fsha(t) for n, t in files.items() if n != 'manifest.json'}}, indent=2, sort_keys=True) + '\n'


# ---------------------------------------------------------------- what the packs leave on a State's books, and the workflow generated from a look (this file's own second writing)
def books(packs):
    """What a list of packs leaves on the books, as far as a generated workflow reads them: a later pack names the scope and the goals anew, an approved rule stands under
    its head, a method under its id, grants are added and revoked pack by pack, and the budget starts at the kernel's own."""
    b = {'scope': 'orgA/fulfillment', 'goals': [], 'rules': {}, 'methods': {}, 'providers': {}, 'grants': set(), 'budget': {'compute': 10, 'money': 10, 'attention': 3},
         'preference': ['compute', 'money', 'attention']}
    for p in packs:
        b['scope'] = p.get('scope', b['scope'])
        b['goals'] = list(p['goals']) if 'goals' in p else b['goals']
        for r in p.get('rules', []):
            if r.get('approved', False):
                b['rules'][r['head']] = r
        for m in p.get('methods', []):
            b['methods'][m['id']] = m
        b['providers'].update(p.get('providers', {}))
        b['grants'] = (b['grants'] | set(p.get('grants', []))) - set(p.get('revoke_grants', []))
        b['budget'].update(p.get('budget', {}))
        b['preference'] = p.get('preference', b['preference'])
    return b


def stored(packs):
    """The rows a list of packs leaves on the books, by scope and fact, in the order each was first stored: a pack names its scope before its rows, a row that is not
    verified is not stored, and a decision stands until another decision replaces it."""
    scope, rows = 'orgA/fulfillment', {}
    for p in packs:
        scope = p.get('scope', scope)
        for o in p.get('evidence', []):
            at = o.get('scope', scope)
            key = at + '|' + o['predicate']
            if o.get('verified', False) and not (rows.get(key, {}).get('final') and not o.get('final')):
                rows[key] = dict(o, scope=at)
    return rows


def step_slug(name):   # the generator's name for a step
    out = ''.join(ch if ch.isalnum() else '-' for ch in str(name).lower()).strip('-')
    while '--' in out:
        out = out.replace('--', '-')
    return out or 'goal'


def generated(r, b, sha):
    """The implementation the generator writes for a look r of the kernel on the books b: the workflow (a step that records the goal, one step per step of the plan in the
    order the kernel selected them, a step that shows the result; one edge per prerequisite a step takes from an earlier step), its atoms and the scaffold of the
    department. Proposal only, every method step in the local sandbox."""
    goal, scope, M = r['goal'], r['scope'], b['methods']
    steps_of_plan = list(dict.fromkeys(r.get('actions', []) + r.get('skipped', []) + r.get('waits', []) + r.get('pending', [])))
    chosen = next((e['data'].get('actions', []) for e in r['trace'] if e['operation'] == 'SELECT'), [])
    actions = sorted(steps_of_plan, key=lambda mid: chosen.index(mid) if mid in chosen else -1)
    ran, skipped = [x['method'] for x in r.get('model_receipts', [])], list(r.get('skipped', []))
    spend = lambda mids: {k: sum(M.get(a, {}).get('cost', {}).get(k, 0) for a in mids) for k in b['budget']}
    cost = spend(actions) if r.get('waits') or skipped or r.get('stopped') else r.get('cost')
    still = [a for a in actions if a not in ran and a not in r.get('waits', []) and a not in skipped]
    budget = (f'plan cost {canon(cost)} within {canon(b["budget"])}' if still == actions else
              f'plan cost {canon(cost)}, of which still to pay {canon(spend(still))} within {canon(b["budget"])}')
    steps = [{'id': 'record-intent', 'host': 'codex', 'sandbox': 'read-only', 'action': f'log the goal {goal}, the scope {scope} and the selected plan to the execution record',
              'verify': 'an execution row exists for this run'}]
    asked_before, made_by, taken = set(r.get('waits', [])) - set(r.get('actions', [])), {}, {'record-intent', 'show-it'}
    for mid in actions:
        m = M.get(mid, {})
        price, needs = ', '.join(f'{k} {v}' for k, v in sorted(m.get('cost', {}).items())), ', '.join(m.get('requires', [])) or 'none'
        sid = next(x for x in (step_slug(mid) + ('' if n == 1 else f'-{n}') for n in range(1, len(taken) + 2)) if x not in taken)
        taken.add(sid)
        steps.append({'id': sid, 'host': m.get('provider') or 'claude-effector', 'sandbox': 'local-model-only', 'method': mid, 'kind': m.get('action'), 'effect': m.get('effect'),
                      'requires': list(m.get('requires', [])), 'after': [] if mid in asked_before else list(dict.fromkeys(made_by[q] for q in m.get('requires', []) if q in made_by)),
                      'grant': m.get('grant'), 'cost': dict(m.get('cost', {})),
                      'action': f"make {m.get('effect')} true by {mid} (needs {needs}; grant {m.get('grant')}; cost {price or 'none'}); the owner stamps the ask before any real effect",
                      'verify': f"{m.get('effect')} observed TRUE from an independent source, not from the receipt"})
        if m.get('action') == 'ask':
            to = m.get('ask_to', 'owner')
            steps[-1].update(waits_for=to, action=f"ask {to}: {m.get('question') or 'is ' + str(m.get('effect')) + ' true?'} Then wait: nothing after this step runs "
                                                  f"until the answer arrives, and a no is final (grant {m.get('grant')}; cost {price or 'none'})",
                             verify=f"{m.get('effect')} answered TRUE or FALSE by {to}, the answer citing this ask's receipt")
        made_by.setdefault(m.get('effect'), sid)
    steps.append({'id': 'show-it', 'host': 'claude-effector', 'sandbox': 'read-only', 'action': 'show the goal, the plan, the gates and the record; say what waits on a stamp',
                  'verify': f'the page lists {len(actions) + 2} steps and the goal {goal}'})
    name = step_slug(goal)
    effect_of = {x['id']: x.get('effect') for x in steps if x.get('method')}
    workflow = {'schema': 'sutra-native/user-kit-workflow/1', 'id': 'W-' + name, 'name': f'Make {goal} true for {scope}', 'version': '0.1.0-proposed',
                'created': 'generated; the deploy step stamps the date', 'source': f"Core Algorithm plan for {goal}, trace root {r.get('trace_root_sha256')}",
                'deploy': "PROPOSED_ONLY: review, then cp to ~/.sutra-native/user-kit/workflows/ under the owner's stamp",
                'trigger': {'kind': 'intent', 'utterance_patterns': [f"(make|complete) {name.replace('-', ' ')}"], 'input': f'the standing goal {goal} in scope {scope}'},
                'steps': steps,
                'edges': [{'from': a, 'to': x['id'], 'via': q} for x in steps if x.get('method') for q in dict.fromkeys(x.get('requires', [])) for a in dict.fromkeys(x.get('after', []))
                          if effect_of.get(a) == q],
                'verify': f"{goal} observed TRUE from an independent source; every step's receipt present; budget not exceeded ({budget})",
                'enforcement': {'current': 'PROPOSED_ONLY: generated from a local plan; nothing executed; every real effect is an ask the owner stamps',
                                'planned': 'the daemon runs the steps as asks; independent verification closes each'}}
    if any(spend(still)[k] > b['budget'][k] for k in b['budget']):
        workflow['over_budget'] = spend(still)
    if r.get('work_state') == 'blocked':
        workflow['blocked'] = r.get('status')
    if r.get('stopped'):
        workflow['stopped'] = dict(r['stopped'])
    rule, rules = b['rules'].get(goal), []
    for mid in actions:
        m = M.get(mid, {})
        g = m.get('grant')
        rules.append({'tag': 'go', 'line': f"{mid} may run: grant {g} is held; provider {m.get('provider')}"} if g and g in b['grants'] else
                     {'tag': 'ask', 'line': f'{mid} needs grant {g} before it runs'} if g else {'tag': 'ask', 'line': f'{mid} has no grant declared; ask before it runs'})
    rules.append({'tag': 'refuse', 'line': 'any action kind without a registered handler (registered: ' + ', '.join(sorted(KINDS)) + ')'})
    rules += [{'tag': 'always', 'line': line} for line in INVARIANTS]
    scaffold = {'title': f'Department for {goal}', 'scope': scope, 'purpose': f'keep {goal} true for {scope}, by approved rules, with verified evidence',
                'done_when': [' and '.join(f'{c} is TRUE' for c in branch) for branch in rule['branches']] if rule else [f'{goal} is observed TRUE from a verified source'],
                'rules': rules,
                'functions': {'identity': 'the goal and the done lines above', 'adaptation': "needs from new rules and facts (the kernel's REFINE and QUERY)",
                              'priority': f"preference {list(b['preference'])} over budget {dict(b['budget'])}",
                              'coordination': f"{len(actions)} method steps in order, providers {sorted({M.get(a, {}).get('provider') for a in actions} - {None})}",
                              'audit': 'hash-chained trace; independent verifier; local receipts never count as external proof'}}
    atoms = [{'id': f'A{i}', 'workflow': workflow['id'], 'name': x.get('method', x['id']), 'owner': 'proposed-department', 'status': 'open', 'goal': {'text': goal},
              'constraints': [f"grant {x.get('grant')}", f"cost {canon(x.get('cost', {}))}", 'LOCAL_REFERENCE_ONLY'], 'context': {'scope': scope, 'requires': x.get('requires', [])},
              'work': {'method': x.get('method'), 'host': x['host']}, 'verify': {'check': x['verify'], 'met': False, 'evidence': None}}
             for i, x in enumerate(steps, 1) if x.get('method')]
    impl = {'schema': 'core-algorithm/implementation/1', 'status': 'PROPOSED_ONLY',
            'plan': dict({'goal': goal, 'scope': scope, 'status': r.get('status'), 'actions': actions, 'cost': cost, 'ran': ran, 'spent': spend(ran), 'waits': list(r.get('waits', []))},
                         **({'skipped': skipped} if skipped else {}), trace_root_sha256=r.get('trace_root_sha256')),
            'workflow': workflow, 'atoms': atoms, 'scaffold': scaffold, 'claim': 'generated from a local plan; not executed; not registered; a runnable shape, not a run'}
    impl['implementation_sha256'] = sha(impl)
    return impl


def problems_of(wf):   # what is wrong with a workflow as the runtime would take it: empty when it has the shape and is proposal only
    out = [f'missing {f}' for f in ('id', 'name', 'version', 'source', 'trigger', 'steps', 'verify', 'enforcement') if f not in wf]
    for i, x in enumerate(wf.get('steps', [])):
        out += [f'step {i} missing {f}' for f in ('id', 'host', 'sandbox', 'action', 'verify') if f not in x]
        if x.get('method') and x.get('sandbox') != 'local-model-only':
            out.append(f'step {i} is a method step without the local sandbox')
    pos = {x.get('id'): i for i, x in enumerate(wf.get('steps', []))}
    if len(pos) != len(wf.get('steps', [])):
        out.append('two steps share one id')
    for e in wf.get('edges', []):
        if e.get('from') not in pos or e.get('to') not in pos:
            out.append(f"edge {e.get('from')} -> {e.get('to')} names a step that is not in the workflow")
        elif pos[e['from']] >= pos[e['to']]:
            out.append(f"step {e['to']} comes before its prerequisite {e['from']}")
    if wf.get('blocked'):
        out.append(f"the plan is blocked ({wf['blocked']}): no step here makes the goal true")
    if wf.get('stopped'):
        out.append(f"the run stopped at {wf['stopped'].get('method')}: {wf['stopped'].get('reason')}")
    if wf.get('over_budget'):
        out.append(f"the steps still to pay cost more than the budget left ({canon(wf['over_budget'])})")
    if 'PROPOSED_ONLY' not in str(wf.get('enforcement', {}).get('current', '')):
        out.append('enforcement.current is not PROPOSED_ONLY')
    return out


def checklist(wf, sha):   # the standard's evidence rows for a workflow: one verified row per check, versioned by the digest of what was checked
    version = 'wf-' + sha(wf)[:12]
    return [{'predicate': p, 'truth': 'TRUE' if test(wf) else 'FALSE', 'verified': True, 'source': 'adapter:standards/workflow@1', 'version': version, 'checked': wf.get('id'), 'question': q}
            for p, q, test in CHECKLIST]


# ---------------------------------------------------------------- the system, worked out again from the kernel's results and the packs
def choice_of(asked, cat, row):
    """Who chose the domain: the caller (row), or the stand-in that counts the words an ask shares with each domain's vocabulary and chooses nothing on a tie or without one."""
    rank = [{'domain': i, 'shared_words': len(w), 'words': w} for w, i in sorted(((sorted(words_of(asked) & {x.lower() for x in c['words']}), c['id']) for c in cat), key=lambda x: (-len(x[0]), x[1]))]
    top = rank[0]['shared_words'] if rank else 0
    tied = [r['domain'] for r in rank if r['shared_words'] == top] if top else []
    if row:
        return {'domain': row['id'], 'how': 'the caller', 'ranking': rank, 'tied': []}
    if len(tied) == 1:
        return {'domain': tied[0], 'how': 'a word match on ' + ', '.join(rank[0]['words']) + ' (a stand-in: a person or an agent should confirm the choice)', 'ranking': rank, 'tied': []}
    return {'domain': None, 'how': f'nobody: {len(tied)} reviewed domains share the same number of words with the ask' if tied else 'nobody: no reviewed domain shares a word with the ask',
            'ranking': rank, 'tied': tied}


def draft_of(asked, sha):
    """The draft a system without a domain carries, and the kernel's dry look at it, whole: a draft holds one rule that nobody approved and no method, so the kernel accepts
    the goal, finds what it means drafted and not reviewed, blocks and ends. Four rows, hashed here."""
    name = slug(asked)
    goal = name.replace('-', '_')
    pack = {'schema': 'sutra-extension/2', 'id': 'draft-' + name, 'scope': 'draft/unreviewed', 'goals': [goal],
            'rules': [{'id': 'R-DRAFT@1', 'head': goal, 'branches': [['first_condition_to_name']], 'approved': False, 'source': 'draft/unreviewed: a template from the page builder, not knowledge'}]}
    status, trace, prev = 'SEMANTICS_UNAPPROVED', [], 'GENESIS'
    for op, data in (('GOAL_ACCEPTED', {'goal': goal, 'scope': pack['scope']}), (status, {'predicate': goal}), ('BLOCK', {'reason': status, 'all_reasons': [status]}),
                     ('TERMINAL', {'status': status, 'work_state': 'blocked'})):
        row = {'seq': len(trace) + 1, 'prev_sha256': prev, 'operation': op, 'data': data}
        row['sha256'] = prev = sha(row)
        trace.append(row)
    look = {'goal': goal, 'scope': pack['scope'], 'goal_truth_before': 'UNKNOWN', 'work_state': 'blocked', 'actions': [], 'needs': [], 'cost': None, 'proof': [], 'model_receipts': [],
            'candidates': [], 'selected_branch': None, 'stop_reasons': [status], 'provenance': [{'pack': pack['id'], 'sha256': sha(pack)}], 'status': status, 'pareto_options': 0,
            'trace': trace, 'trace_root_sha256': prev, 'claim': CLAIM}
    return pack, look


def stops_of(look):
    """Where a look of the kernel found no plan, read off its trace: each stop reason with the condition its row names, in the order of the trace. Every reason the look
    carries must be named by a row; a plan the gate turned away and a circle are not among the looks on record."""
    out = []
    for e in look['trace']:
        if e['operation'] in look['stop_reasons'] and type(e['data'].get('predicate')) is str:
            row = {'reason': e['operation'], 'at': [e['data']['predicate']], 'detail': None}
            out += [] if row in out else [row]
    if {x['reason'] for x in out} != set(look['stop_reasons']) or not out or any(e['operation'] in ('ADMISSION', 'CYCLE_LIMIT') for e in look['trace']):
        raise NoWords('a look without a plan that names no condition, or one the gate turned away')
    return out


def system_of(asked, cat, row, rec, handlers, pk, sha):
    """One system as the builder must have written it: from the words, the catalogue (or the exhibit's row when the caller chose), the pack files, the code the record
    holds behind the four kinds, and the kernel's results in record.json. Nothing here reads system.json. Raises when a result is in a state this file has no words for."""
    s = {'schema': 'core-algorithm/system/4', 'status': 'PROPOSED_ONLY', 'asked': asked, 'choice': choice_of(asked, cat, row), 'kinds': list(KINDS),
         'handlers': {kind: {hook: {'function': fn, 'file': handlers[kind]['file'], 'sha256': handlers[kind]['sha256']} for hook, fn in HOOKS[kind].items()} for kind in KINDS},
         'catalogue': [{'id': c['id'], 'title': c['title'], 'say': c['say']} for c in cat]}
    if s['choice']['domain'] is None:   # nothing was guessed: the draft, and the kernel's own answer to it
        pack, look = draft_of(asked, sha)
        s.update({'verdict': 'NO_DOMAIN', 'labels': {}, 'file_names': list(DRAFT_FILES),
                  'draft': {'pack': pack, 'kernel_status': look['status'], 'trace_root_sha256': look['trace_root_sha256'], 'to_write': list(TO_WRITE)}})
        s['system_sha256'] = sha(s)
        return s
    row = row or [c for c in cat if c['id'] == s['choice']['domain']][0]
    packs, standard = [pk(n) for n in row['packs']], [pk(n) for n in STANDARD]
    b, plan, runs, after, judged = books(packs), rec['plan'], rec['runs'], rec['after'], rec['standard']
    if b['goals'] != [row['goal']] or plan['goal'] != row['goal']:
        raise NoWords('the packs leave another goal than the row names')
    impl = generated(plan, b, sha)
    wf = impl['workflow']
    problems = problems_of(wf)
    asks = []
    for i in range(len(runs) - 1):   # each question is the receipt the run before it parked on; what each answer led to is the next run on that path
        issued, look = runs[i]['model_receipts'][-1], rec['no_after'][i]
        asks.append({'fact': issued['ask']['predicate'], 'question': issued['ask']['question'], 'to': issued['ask']['to'], 'asked_by': issued['method'], 'receipt_sha256': issued['sha256'],
                     'if_yes': brief(runs[i + 1]), 'if_no': dict(brief(rec['no_runs'][i]), goal_held=held(look) if look else None)})
    if plan['status'] != 'PLAN_READY':   # the kernel has no plan: nothing ran, nothing was judged, and every row is a row of its own trace
        if runs or rec['no_runs'] or rec['no_after'] or after or judged:
            raise NoWords('a run without a plan')
        verdict, rows = 'BLOCKED', stops_of(plan)
    else:
        last, planned = runs[-1], next(e['data']['actions'] for e in plan['trace'] if e['operation'] == 'SELECT')
        ran, skipped = [x['method'] for r in runs for x in r['model_receipts']], [m for r in runs for m in r.get('skipped', [])]
        chosen = [m for r in runs for m in r['actions'] + r.get('pending', []) + r.get('skipped', [])]   # every step a run selected: ran, skipped, stopped or still to run
        if [m for m in chosen if m not in planned] or (last['work_state'] == 'completed' and [m for m in planned if m not in ran and m not in skipped]) or problems:
            raise NoWords('another route than the plan shown, or a workflow that is not well formed')
        if last['status'] == 'STEP_STOPPED':   # the kernel's own record of a step that could not run
            rows = [{'reason': 'STEP_STOPPED', 'at': [last['stopped']['method']], 'detail': last['stopped']['reason']}]
        elif last['work_state'] == 'blocked':   # after an answer the kernel found no plan: its own trace says why
            rows = stops_of(last)
        elif last['work_state'] != 'completed':
            raise NoWords('a run that still waits after every answer')
        else:
            rows = [] if held(after) else [{'reason': 'GOAL_NOT_HELD', 'at': [plan['goal']], 'detail': after['status']}]
        if bool(rows) != (judged is None) or (judged is not None and judged['status'] != 'SUPPORTED_BY_EVIDENCE'):
            raise NoWords('a standard judged for a path that did not get there, or not met')
        verdict = 'NOT_READY' if rows else ('WAITING' if asks else 'READY')
    if judged is None:
        st = {'goal': None, 'rule': None, 'status': 'NOT_APPLICABLE', 'registrable': None, 'workflow': wf['id'], 'evidence': [], 'checks': [], 'trace_root_sha256': None}
    else:   # the kernel's judgement of the workflow written beside the page, on this file's own reading of that workflow
        facts = checklist(wf, sha)
        st = {'goal': judged['goal'], 'rule': books(standard)['rules'].get(judged['goal'], {}).get('id'), 'status': judged['status'], 'registrable': judged['status'] == 'SUPPORTED_BY_EVIDENCE',
              'workflow': wf.get('id'), 'evidence': facts, 'checks': [{'check': x['predicate'], 'question': x['question'], 'truth': x['truth']} for x in facts],
              'trace_root_sha256': judged['trace_root_sha256']}
    rule = b['rules'].get(plan['goal'])
    s.update({'domain': {k: row[k] for k in ('id', 'title', 'goal', 'say', 'packs')},
              'pack_digests': {'domain': [{'pack': p['id'], 'sha256': sha(p)} for p in packs], 'standard': [{'pack': p['id'], 'sha256': sha(p)} for p in standard]},
              'verdict': verdict, 'labels': dict(row.get('labels', {})), 'done_when': [list(branch) for branch in rule['branches']] if rule else [[plan['goal']]],
              'plan': dict(brief(plan), goal=plan['goal'], scope=plan['scope']), 'blocked_at': rows, 'implementation': impl, 'workflow_problems': problems, 'standard': st,
              'model_run': {'path': [brief(r) for r in runs], 'asks': asks, 'after': brief(after) if after else None, 'goal_held': held(after) if after else None, 'effects_missing': []},
              'file_names': list(BUILT_FILES)})
    s['system_sha256'] = sha(s)
    return s


# ---------------------------------------------------------------- the page, rendered again from the system and the first look's chain
def wrap(text, n, lines):   # words on at most `lines` lines of at most n characters; what does not fit ends in three dots
    out, rest = [], str(text).split(' ')
    while rest and len(out) < lines:
        line = rest.pop(0)
        while rest and len(line) + 1 + len(rest[0]) <= n:
            line += ' ' + rest.pop(0)
        out.append(line)
    if rest:
        while len(out[-1]) + 3 > n and ' ' in out[-1]:
            out[-1] = out[-1].rsplit(' ', 1)[0]
        out[-1] += '...'
    return [short(line, n) for line in out]


def page_of(s, rec, style):
    """The page of a system on record, whole. The words are this file's own; a system in a state it has no words for raises."""
    v, L = s['verdict'], lambda x: str(s.get('labels', {}).get(x, x))
    names = lambda xs: ', '.join(L(x) for x in xs)
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">',
           f'<title>{esc(short(s["asked"], 60))}</title><style>{style}</style></head><body><main>',
           f'<p><span class="tag">Proposal only</span><span class="tag">{WORDS[v]}</span></p>', f'<h1>{esc(s["asked"])}</h1>']
    if v == 'NO_DOMAIN':
        d, tied = s['draft'], s['choice']['tied']
        titles = ', '.join(c['title'] for c in s['catalogue'] if c['id'] in tied)
        lead = (f'These words fit {len(tied)} reviewed domains equally ({titles}), so nothing was guessed. Someone has to choose one.' if tied else
                'No reviewed domain shares a word with these words, so nothing was guessed. Below is what someone has to write down first.')
        out.append(f'<div class="verdict {v}"><p class="lead">{esc(lead)}</p></div>')
        if tied:
            out.append('<p class="hint">To build one of them, name it: ' + ' or '.join(f'<code>--domain {esc(i)}</code>' for i in tied) + '.</p>')
        out += ['<h2>What the builder can build today</h2><div class="scroll"><table><tr><th>Domain</th><th>Its name</th><th>You would say</th></tr>',
                ''.join(f'<tr><td>{esc(c["title"])}</td><td><code>{esc(c["id"])}</code></td><td>{esc(c["say"])}</td></tr>' for c in s['catalogue']), '</table></div>',
                '<h2>What someone has to write down first</h2><ol>', ''.join(f'<li>{esc(x)}</li>' for x in d['to_write']), '</ol>',
                f'<h2>What the kernel says about a draft</h2><p><span class="tag">{esc(d["kernel_status"])}</span> {esc(cap(say(d["kernel_status"])))}. '
                'A draft is a template, not knowledge: while its rule is unapproved, and no method makes the goal itself, the kernel plans nothing from it.</p>',
                f'<details><summary>The draft pack</summary><pre>{esc(json.dumps(d["pack"], indent=2, ensure_ascii=False))}</pre></details>',
                f'<details><summary>How a new domain gets in</summary><p>{esc(NEW_DOMAIN)}</p></details>']
        trace = rec['draft']['trace']
    else:
        wf, sc, run, plan, st, rows = s['implementation']['workflow'], s['implementation']['scaffold'], s['model_run'], s['plan'], s['standard'], s['blocked_at']
        steps, asks, path = [x for x in wf['steps'] if x.get('method')], run['asks'], run['path']
        n, last = len(steps), path[-1] if path else None
        if len(asks) > 1 or run['effects_missing']:
            raise NoWords('several questions, or a step whose effect does not hold')
        ran, skipped = {x['method'] for r in path for x in r['receipts']}, list(dict.fromkeys(m for r in path for m in r['skipped']))
        stopped = last['stopped']['method'] if last and last['stopped'] else None
        unreached = {x['method'] for x in steps} - ran - set(skipped) if v == 'NOT_READY' and path else set()
        said = ', after ' + ', '.join(dict.fromkeys(a['to'] for a in asks)) + ' said yes' if asks else ''
        count = 'one step' if n == 1 else f'{n} steps in order'
        # ---- the first sentence
        if v == 'READY':
            tail = '' if not skipped else ' One of them is already true at its turn and is skipped.' if len(skipped) == 1 else f' {len(skipped)} of them are already true at their turn and are skipped.'
            lead = f'Ready: {count}, and nothing waits on anyone.' + tail if n else 'Already true: the facts support the goal and no step is needed.'
        elif v == 'WAITING':
            lead = f"Waiting on {asks[0]['to']}: one question has to be answered " + (f'before the rest of the {n} steps can run' if path[0]['pending'] else 'and nothing else is left to run') + '.'
        else:   # the row the first sentence names: the first one; of a look that found no plan, the row of the reason the kernel names that look with
            look = plan if v == 'BLOCKED' else last if last['work_state'] == 'blocked' else None
            row = next((x for x in rows if x['reason'] == look['status']), rows[0]) if look else rows[0]
            detail = '' if not row['detail'] else AFTER.get(row['detail']) or say(row['detail']) if row['reason'] == 'GOAL_NOT_HELD' else str(row['detail'])
            named = f" ({names(row['at'])}" + (f'; {detail}' if detail else '') + ')'
            if v == 'BLOCKED':
                lead = f"Cannot start: {say(row['reason'])}{named}."
            elif row['reason'] == 'STEP_STOPPED':
                lead = f"A plan was found, but it stops in the local model{said}: the step {names(row['at'])} cannot run ({row['detail']})."
            elif row['reason'] == 'GOAL_NOT_HELD':
                lead = f"A plan was found, but it does not get there in the local model{said}: every step ran, and afterwards it still does not hold that {names(row['at'])} ({detail})."
            else:
                lead = f"A plan was found, but it does not get there in the local model{said}: the kernel has no plan left, because {say(row['reason'])}{named}."
        out += [f'<div class="verdict {v}"><p class="lead">{esc(lead)}</p></div>',
                f'<p class="hint">Built from the reviewed domain <b>{esc(s["domain"]["title"])}</b>, chosen by {esc(s["choice"]["how"])}.</p>']
        # ---- the picture: one box per method step, one arrow per prerequisite, columns by dependency depth
        marks = {}
        if v == 'WAITING':
            marks.update({m: ('later', 'asked after the answer' if {x['method']: x.get('kind') for x in steps}.get(m) == 'ask' else 'after the answer') for m in path[0]['pending']})
        if v == 'NOT_READY' and path:
            marks.update({m: ('later', 'not reached') for m in unreached})
            if stopped:
                marks[stopped] = ('stop', 'stops here')
        for m in skipped:
            marks.setdefault(m, ('skipped', 'already true: skipped'))
        pic = ''
        if steps:
            level, columns, cells, W, GX, GY, TOP = {}, {}, {}, 174, 40, 30, 30
            for x in steps:   # steps arrive in dependency order, so every prerequisite already has its level
                level[x['id']] = 1 + max([level[a] for a in x.get('after', []) if a in level], default=-1)
                columns.setdefault(level[x['id']], []).append(x['id'])
                cls, mark = marks.get(x['method'], ('', ''))
                cells[x['id']] = (wrap(L(x['method']), 23, 2), [short('asks ' + x['waits_for'], 27)] if x.get('waits_for') else wrap(L(x.get('effect')), 27, 2), mark,
                                  ' '.join(c for c in ('ask' if x.get('waits_for') else '', cls) if c))
            H = max(56, 19 + 15 * max(len(t) + len(sub) + bool(mark) for t, sub, mark, _ in cells.values()))
            width, height = (max(columns) + 1) * (W + GX) - GX + 2, TOP + max(len(c) for c in columns.values()) * (H + GY) - GY + 2
            at = {sid: (1 + lv * (W + GX), TOP + i * (H + GY)) for lv, ids in columns.items() for i, sid in enumerate(ids)}
            parts, far = [f'<svg class="plan" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="The plan as steps and the order they depend on">'], 0
            for ed in wf.get('edges', []):
                (x1, y1), (x2, y2) = at[ed['from']], at[ed['to']]
                sy, ey = y1 + H // 2, y2 + H // 2
                if level[ed['to']] - level[ed['from']] == 1:   # to the next column: one straight line through the gap
                    parts.append(f'<path class="edge" d="M{x1 + W},{sy} L{x2 - 6},{ey}"/><polygon class="head" points="{x2},{ey} {x2 - 7},{ey - 4} {x2 - 7},{ey + 4}"/>')
                else:   # skips a column: out into the gap, along the gap above the row of its step, down into the step
                    off = (far % 5 - 2) * 4
                    far += 1
                    gx, lane, tx = x1 + W + GX // 2 + off, y2 - GY // 2 + off, x2 + W // 2 + off * 3
                    parts.append(f'<path class="edge" d="M{x1 + W},{sy} L{gx},{sy} L{gx},{lane} L{tx},{lane} L{tx},{y2 - 6}"/>'
                                 f'<polygon class="head" points="{tx},{y2} {tx - 4},{y2 - 7} {tx + 4},{y2 - 7}"/>')
            for x in steps:
                (bx, by), (title, sub, mark, cls) = at[x['id']], cells[x['id']]
                tip = f"{x['method']} asks {x['waits_for']} whether {x.get('effect')}" if x.get('waits_for') else f"{x['method']} makes {x.get('effect')}"
                lines = [('', t) for t in title] + [(' class="sub"', t) for t in sub] + ([(' class="mark"', mark)] if mark else [])
                parts.append(f'<g class="{cls}"><title>{esc(tip)}</title><rect x="{bx}" y="{by}" width="{W}" height="{H}" rx="8"/>'
                             + ''.join(f'<text{kind} x="{bx + 12}" y="{by + 21 + 15 * i}">{esc(line)}</text>' for i, (kind, line) in enumerate(lines)) + '</g>')
            pic = ''.join(parts) + '</svg>'
        # ---- why this picture
        goal = L(plan['goal'])
        if v == 'BLOCKED':
            claim = f'No plan can yet make it true that {goal}.'
        elif n == 0:
            claim = f'Nothing needs doing: the facts already support that {goal}.'
        elif v == 'NOT_READY':
            claim = ('On paper this one step makes' if n == 1 else f'On paper these {n} steps, in this order, make') + f' it true that {goal}. In the local model the plan does not get there; the first lines of this page say where.'
        else:
            claim = ('This one step makes' if n == 1 else f'These {n} steps, in this order, make') + f' it true that {goal}' + (f", if {asks[0]['to']} says yes" if v == 'WAITING' else '') + '.'
        why = []
        for x in steps:   # one clause per step: what it makes true, and what the local model showed when that differs
            step, what, asked = L(x['method']), L(x.get('effect')), x.get('waits_for')
            if x['method'] in skipped:
                why.append((f'{asked} is not asked' if asked else f'{step} is skipped') + f', because it is already true that {what}')
            elif x['method'] == stopped:
                why.append(f'{step} should make it true that {what} (in the local model it could not run)')
            elif x['method'] in unreached:
                why.append((f'{asked} would be asked whether {what}' if asked else f'{step} should make it true that {what}') + ' (not reached in the local model)')
            else:
                why.append(f'{asked} is asked whether {what}' if asked else f'{step} makes it true that {what}')
        cost = f'plan cost {json.dumps(plan["cost"])}; ' if plan['cost'] is not None else ''
        out.append('<h2>The plan</h2>' + (f'<div class="scroll">{pic}</div>' if pic else '<p>No step is needed or possible right now.</p>'))
        out.append(f'<details><summary>{"Why this picture" if pic else "Why there is no picture"}</summary><p><b>Claim.</b> {esc(claim)}</p>'
                   f'<p><b>Why.</b> {esc(cap("; ".join(why) or "no step is part of a plan"))}.</p>'
                   f'<p><b>Evidence.</b> Kernel status {esc(plan["status"])}; {esc(cost)}trace root <code>{esc(plan["trace_root_sha256"])}</code>; '
                   f'workflow problems: {esc("; ".join(s["workflow_problems"]) or "none")}.</p>'
                   '<p><b>What would change it.</b> A new reviewed rule, a changed fact, a revoked grant, a smaller budget or an answer to an open question: the kernel plans again from the record.</p></details>')
        # ---- what stands in the way, what done means
        if v in ('BLOCKED', 'NOT_READY'):
            reason = lambda x: say(x['reason']) + ('' if not x['detail'] else ': ' + (AFTER.get(x['detail']) or say(x['detail']) if x['reason'] == 'GOAL_NOT_HELD' else str(x['detail'])))
            table = ''.join(f'<tr><td>{esc(cap(names(x["at"])))} <code>{esc(", ".join(x["at"]))}</code></td><td>{esc(cap(reason(x)))}</td><td>{esc(cap(unblock(x["reason"])))}</td></tr>' for x in rows)
            out.append(('<h2>Why it cannot start</h2>' if v == 'BLOCKED' else '<h2>What stands in the way</h2>')
                       + '<div class="scroll"><table><tr><th>Where</th><th>Reason</th><th>What would unblock it</th></tr>' + table + '</table></div>')
        done = s['done_when']
        out.append('<h2>What done means</h2>' + ('<p class="hint">Any one of these is enough.</p>' if len(done) > 1 else '')
                   + '<ul>' + ''.join(f'<li>{esc(cap(" and ".join(L(c) for c in branch)))}</li>' for branch in done) + '</ul>')
        # ---- the question, with what each answer leads to as the kernel ran it
        if asks:
            a = asks[0]

            def led(b, goal_held, yes):
                if b['status'] == 'STEP_STOPPED' or b['work_state'] == 'waiting' or b['skipped'] or b['pending']:
                    raise NoWords('an answer after which a step stops, the run waits again, or a step is skipped')
                if b['work_state'] == 'blocked':
                    head = f"The run ends here: {say(b['status'])}."
                elif not b['receipts']:
                    head = 'With this answer the goal holds; no step is left to run.' if goal_held else 'No step is left to run, and the goal still does not hold.'
                elif yes:
                    head = 'The plan runs through in the local model.' if goal_held else 'Every step runs, and afterwards the goal still does not hold.'
                else:
                    head = 'Another route is taken and gets there.' if goal_held else 'Another route is taken, and afterwards the goal still does not hold.'
                return f'<p><b>{esc(head)}</b>' + (f' Ran in the local model: {esc(names(x["method"] for x in b["receipts"]))}.' if b['receipts'] else '') + '</p>'
            out.append(('<h2>Waiting on an answer</h2>' if v == 'WAITING' else '<h2>The questions on the way</h2>')
                       + f'<fieldset class="choice"><legend><b>{esc(cap(a["to"]))}</b> is asked: {esc(a["question"])}</legend>'
                       '<input class="w" type="radio" name="ask0" id="ask0w" checked><label for="ask0w">Not answered yet</label>'
                       '<input class="y" type="radio" name="ask0" id="ask0y"><label for="ask0y">They say yes</label>'
                       '<input class="n" type="radio" name="ask0" id="ask0n"><label for="ask0n">They say no</label>'
                       f'<div class="panel w"><p>{esc(UNANSWERED)}</p></div><div class="panel y">{led(a["if_yes"], run["goal_held"], True)}</div>'
                       f'<div class="panel n">{led(a["if_no"], a["if_no"]["goal_held"], False)}</div></fieldset>'
                       f'<p class="hint">Asked by the step {esc(L(a["asked_by"]))}. The answer must come from {esc(a["to"])} and present the receipt of this question.</p>')
        # ---- the details, folded
        go, need = sum(1 for r in sc['rules'] if r['tag'] == 'go'), sum(1 for r in sc['rules'] if r['tag'] == 'ask')
        who = ('no step is planned' if not go and not need else
               ('one step has its grant' if go == 1 else f'{go} steps have their grant') + (f', {need} {"needs" if need == 1 else "need"} one first' if need else ''))
        out.append('<h2>The details</h2>')
        out.append(f'<details><summary>Who may do what: {who}</summary><ul>' + ''.join(f'<li><b class="t-{esc(r["tag"])}">{esc(r["tag"])}</b> {esc(r["line"])}</li>' for r in sc['rules']) + '</ul></details>')
        if st['status'] != 'NOT_APPLICABLE':
            passed = sum(1 for c in st['checks'] if c['truth'] == 'TRUE')
            out.append(f'<details><summary>The workflow generated on this page has the parts the standard asks for: {"yes" if st["registrable"] else "no"}, {passed} of {len(st["checks"])}</summary>'
                       f'<p>The kernel judged the generated workflow <code>{esc(st["workflow"])}</code> against the reviewed rule <code>{esc(st["rule"])}</code> and answered <code>{esc(st["status"])}</code>. '
                       'This is about the shape of the workflow written below, not about the goal above.</p>'
                       '<div class="scroll"><table><tr><th>Check</th><th>Result</th></tr>' + ''.join(f'<tr><td>{esc(cap(c["question"]))}</td><td>{esc(c["truth"])}</td></tr>' for c in st['checks']) + '</table></div></details>')
        table = ''.join(f'<tr><td>{esc(cap(L(x.get("method", x["id"]))))} <code>{esc(x["id"])}</code></td><td>{esc(", ".join(x.get("after", [])) or "-")}</td><td>{esc(x["action"])}</td><td>{esc(x["verify"])}</td></tr>' for x in wf['steps'])
        out.append(f'<details><summary>The workflow, step by step: {"no method step" if n == 0 else "one method step" if n == 1 else f"{n} method steps"}, between a step that records the goal and a step that shows the result</summary>'
                   '<div class="scroll"><table><tr><th>Step</th><th>After</th><th>What it does</th><th>How it is checked</th></tr>' + table + '</table></div></details>')
        if path:
            with_yes = 'with every question answered yes ' if asks else ''
            if last['stopped']:
                line = f'{with_yes}a step could not run, and the run stopped there'
            elif last['work_state'] == 'blocked':
                line = f"{with_yes}the kernel found no plan: {say(last['status'])}"
            elif not run['goal_held']:
                line = f'{with_yes}every step ran, and the goal still does not hold'
            else:
                line = f'{with_yes}the plan ran through, and the goal is held' if any(r['receipts'] for r in path) else 'nothing had to run: the facts already support the goal'
            how = '' if not asks else ', with every question answered yes' if v == 'WAITING' else ', with 1 question answered yes before it ended'
            listed = lambda xs: esc(', '.join(L(x) for x in xs) or '-')
            what = lambda i, r: esc(cap((f"after {asks[i - 1]['to']} said yes: " if i else '') + say(r['status']) + (f" ({L(r['stopped']['method'])}: {r['stopped']['reason']})" if r['stopped'] else '')))
            table = ''.join(f'<tr><td>{i + 1}</td><td>{what(i, r)}</td><td>{listed(x["method"] for x in r["receipts"])}</td><td>{listed(r["skipped"])}</td><td>{listed(r["pending"])}</td></tr>' for i, r in enumerate(path))
            seen = '' if run['goal_held'] is None else " The kernel's next look finds the goal held." if run['goal_held'] else " The kernel's next look does not find the goal held."
            out.append(f'<details><summary>A run in the local model: {esc(line)}</summary><p>The plan executed against a model of the world{esc(how)}. '
                       f'Nothing real happened: each receipt is marked local only.{esc(seen)}</p>'
                       '<div class="scroll"><table><tr><th>Run</th><th>What happened</th><th>Steps that ran</th><th>Already true, skipped</th><th>Not run</th></tr>' + table + '</table></div></details>')
        out.append(f'<details><summary>The department that would own it</summary><p>{esc(cap(sc["purpose"]))}.</p><div class="scroll"><table><tr><th>Function</th><th>What it holds</th></tr>'
                   + ''.join(f'<tr><td>{esc(cap(k))}</td><td>{esc(val)}</td></tr>' for k, val in sc['functions'].items()) + '</table></div></details>')
        trace = rec['plan']['trace']
    out.append(f'<details><summary>The record: {len(trace)} decisions in a hash chain</summary><p>The kernel logs every decision in a hash chain; these are the decisions of its first look, in order, each with its own hash. '
               'The last hash is the trace root' + (' quoted under the picture' if v != 'NO_DOMAIN' else '') + '. Every look and run behind this page is in <a href="record.json">record.json</a>, whole, so each chain can be recomputed.</p>'
               '<div class="scroll"><table><tr><th>#</th><th>Decision</th><th>Hash</th></tr>'
               + ''.join(f'<tr><td>{esc(r["seq"])}</td><td>{esc(r["operation"])}</td><td><code>{esc(r["sha256"][:16])}</code></td></tr>' for r in trace) + '</table></div></details>')
    out.append('<h2>Files</h2><ul>' + ''.join(f'<li><a href="{esc(name)}">{esc(name)}</a></li>' for name in s['file_names'] if name != 'index.html') + '</ul>')
    out.append('<footer>Built by the Core Algorithm lab from the words above' + (f' and the reviewed domain {esc(s["domain"]["title"])}' if s.get('domain') else '') + '. '
               f'{esc(s["status"])}: nothing on this page has run outside a local model, and running a step for real is outside this lab. '
               f'Domain chosen by {esc(s["choice"]["how"])}. System sha256 <code>{esc(s["system_sha256"])}</code>; the digest of every other file written beside this page is in manifest.json.</footer></main></body></html>')
    return ''.join(out)


def markup_of(page):
    """Every tag and attribute of a page, read strictly: after the doctype a page is tags and text, every tag is `<name attr="value" ...>`, `<name .../>` or `</name>`, no
    comment, no declaration and no other `<` or `>` anywhere. None when a page is anything else."""
    head = '<!doctype html>'
    if not page.startswith(head) or '<!' in page[len(head):]:
        return None
    tags, attrs = set(), []
    for piece in re.split(r'(<[^<>]*>)', page[len(head):]):
        if piece.startswith('<'):
            m = re.fullmatch(r'<(/?)([a-z][a-z0-9]*)((?: [a-zA-Z-]+(?:="[^"<>]*")?)*)(/?)>', piece)
            if not m or (m.group(1) and (m.group(3) or m.group(4))):
                return None
            tags.add(m.group(2))
            attrs += [(m.group(2), k, v) for k, v in re.findall(r' ([a-zA-Z-]+)(?:="([^"<>]*)")?', m.group(3))]
        elif '<' in piece or '>' in piece:
            return None
    return tags, attrs


def drawn_ok(page, wf):
    """The picture of a page as a drawing: one box per method step and no two in one place, one arrow per prerequisite, every arrow leaving the box of its edge's first
    step at the middle of its right side and ending at the box of its second step (at the middle of its left side, or above it), pointing forward and crossing no box,
    all of it inside the picture, which is drawn at its own size."""
    steps = [x['id'] for x in wf['steps'] if x.get('method')]
    if not steps:
        return '<svg' not in page
    rects = [tuple(int(v) for v in r) for r in re.findall(r'<rect x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"', page)]
    paths = [[tuple(int(v) for v in pt.split(',')) for pt in re.findall(r'[ML](\d+,\d+)', d)] for d in re.findall(r'<path class="edge" d="([^"]*)"', page)]
    heads = [tuple(int(v) for v in h.split(',')) for h in re.findall(r'<polygon class="head" points="(\d+,\d+) ', page)]
    size = re.search(r'<svg class="plan" viewBox="0 0 (\d+) (\d+)" width="(\d+)" height="(\d+)"', page)
    if not (len(rects) == len(set(rects)) == len(steps) == page.count('<rect') and len(paths) == len(heads) == len(wf['edges']) == page.count('<path') == page.count('<polygon')
            and page.count('<svg') == 1 and size and size.group(1, 2) == size.group(3, 4)):
        return False
    box, wide, high = dict(zip(steps, rects)), int(size.group(1)), int(size.group(2))
    inside = lambda px, py: any(r[0] < px < r[0] + r[2] and r[1] < py < r[1] + r[3] for r in rects)
    for e, pts, head in zip(wf['edges'], paths, heads):
        a, b = box[e['from']], box[e['to']]
        leaves = pts[0] == (a[0] + a[2], a[1] + a[3] // 2)
        arrives = head in ((b[0], b[1] + b[3] // 2), ) or (head[1] == b[1] and b[0] < head[0] < b[0] + b[2])
        ends = abs(pts[-1][0] - head[0]) + abs(pts[-1][1] - head[1]) <= 6   # the line ends where its head begins
        if not (leaves and arrives and ends and pts[0][0] < head[0] and all(0 <= px <= wide and 0 <= py <= high for px, py in pts)
                and not any(inside(x1 + (x2 - x1) * i / 40, y1 + (y2 - y1) * i / 40) for (x1, y1), (x2, y2) in zip(pts, pts[1:]) for i in range(41))):
            return False
    return all(r[0] + r[2] <= wide and r[1] + r[3] <= high for r in rects)


def rows_of(data, ROOT, sha, check_chain):
    same = lambda a, b: sha(a) == sha(b)   # numbers are compared as JSON: 1 is not true and not 1.0
    seen, packs, found = {}, {}, {}   # read once: a file's text as JSON, a pack file, and what was found about one recorded system

    def parsed(text):   # what is returned is shared: nothing below changes it
        if text not in seen:
            seen[text] = json.loads(text)
        return seen[text]

    def pk(n):
        if n not in packs:
            packs[n] = json.loads((ROOT / 'scenarios' / (n + '.json')).read_text())
        return packs[n]

    def agrees(r, loaded):   # a kernel result against its own trace and the packs it says it ran on (this file's own reading; S201 reads the same results by the verifier's rule)
        t = r['trace']
        rows = lambda op: [e['data'] for e in t if e['operation'] == op]
        receipts, chosen, block, stops = [x['receipt'] for x in rows('LOCAL_EFFECT')], rows('SELECT'), rows('BLOCK'), rows('STEP_STOPPED')
        skips, table = [x['method'] for x in rows('STEP_ALREADY_TRUE')], {m['id']: m for p in loaded for m in p.get('methods', [])}
        if not (set(r) <= RESULT_KEYS and check_chain(t) and r['trace_root_sha256'] == t[-1]['sha256'] and same(r.get('claim'), CLAIM)
                and t[0]['operation'] == 'GOAL_ACCEPTED' and same(t[0]['data'], {'goal': r['goal'], 'scope': r['scope']})
                and t[-1]['operation'] == 'TERMINAL' and same(t[-1]['data'], {'status': r['status'], 'work_state': r['work_state']})
                and same(r['provenance'], [{'pack': p['id'], 'sha256': sha(p)} for p in loaded])
                and same(receipts, r['model_receipts']) and all(x['status'] == 'LOCAL_ONLY' and x['sha256'] == sha({k: v for k, v in x.items() if k != 'sha256'}) for x in receipts)
                and len(chosen) + len(block) == 1 and len(stops) <= 1):
            return False
        if block:
            return (same([r['status'], r['stop_reasons'], r['actions'], r['work_state'], receipts, r['cost']], [block[0]['reason'], block[0]['all_reasons'], [], 'blocked', [], None])
                    and block[0]['reason'] in block[0]['all_reasons'] and 'pending' not in r and 'stopped' not in r and 'skipped' not in r)
        total = lambda mids: {dim: sum(table[m].get('cost', {}).get(dim, 0) for m in mids) for dim in chosen[0]['full_cost']}
        state = {'ready': 'PLAN_READY', 'waiting': 'WAITING', 'stopped': 'STEP_STOPPED', 'completed': 'LOCAL_MODEL_EFFECTS_RECORDED' if receipts else 'SUPPORTED_BY_EVIDENCE'}.get(r['work_state'])
        return (r['status'] == state and r['stop_reasons'] == [] and [a for a in chosen[0]['actions'] if a not in skips] == r['actions'] + r.get('pending', []) and r.get('skipped', []) == skips
                and set(chosen[0]['actions']) <= set(table) and same(chosen[0]['full_cost'], total(chosen[0]['actions'])) and same(r['cost'], total(r['actions']))
                and [x['method'] for x in receipts] == (r['actions'] if r['work_state'] != 'ready' else [])
                and same(r.get('stopped'), {'method': stops[0]['method'], 'reason': stops[0]['reason']} if stops else None)
                and (not stops or (r['work_state'] == 'stopped' and r['pending'][:1] == [stops[0]['method']])))

    def whole(e, s):   # S120: the closed list of file names, every file a text, the manifest, the folder's name, the digest; the files of the workflow, the atoms, the scaffold or the draft are the system's own parts
        files = e['files']
        parts = ({'draft-pack.json': s['draft']['pack']} if s['verdict'] == 'NO_DOMAIN' else
                 {'workflow.json': s['implementation']['workflow'], 'atoms.json': s['implementation']['atoms'], 'scaffold.json': s['implementation']['scaffold']})
        return (all(type(t) is str for t in files.values()) and list(s['file_names']) == (DRAFT_FILES if s['verdict'] == 'NO_DOMAIN' else BUILT_FILES) and sorted(files) == sorted(s['file_names'])
                and s['system_sha256'] == sha({k: v for k, v in s.items() if k != 'system_sha256'}) and files['manifest.json'] == manifest_of(files, s['system_sha256'])
                and e['folder'] == slug(s['asked']) + '-' + fsha(files['manifest.json'])[:16] and all(ch in 'abcdefghijklmnopqrstuvwxyz0123456789-' for ch in e['folder'])
                and all(files[name] == dump(part) for name, part in parts.items()))

    def record_ok(e, rec, row):   # S121: every look and run is a kernel result that agrees with its own trace and its packs, the looks beside the files are those of record.json, and each question is closed in the kernel's own chain
        if rec.get('schema') != 'core-algorithm/system-record/1':
            return False
        if row is None:   # no domain: the one look is at the draft, and this file makes that look itself
            return False
        domain, standard = [pk(n) for n in row['packs']], [pk(n) for n in STANDARD]
        plan, runs = rec['plan'], rec['runs']
        ok = (sorted(rec) == ['after', 'no_after', 'no_runs', 'plan', 'runs', 'schema', 'standard'] and type(e.get('looks')) is dict and sorted(e['looks']) == ['runs'] and same(e['looks']['runs'], looks_of(rec))
              and all(agrees(r, domain) and r['goal'] == row['goal'] for r in looks_of(dict(rec, standard=None))) and (rec['standard'] is None or agrees(rec['standard'], standard))
              and max(len(runs) - 1, 0) == len(rec['no_runs']) == len(rec['no_after']) and (plan['status'] == 'PLAN_READY') == bool(runs) and plan['work_state'] in ('ready', 'blocked')
              and (rec['after'] is not None) == (bool(runs) and runs[-1]['work_state'] == 'completed') and (rec['after'] is None or rec['after']['work_state'] in ('ready', 'blocked'))
              and (not runs or same(plan['trace'][:-1], runs[0]['trace'][:len(plan['trace']) - 1])))   # the first look and the first run planned alike: the look's rows open the run's chain
        for i in range(len(runs) - 1 if ok else 0):   # each question is the receipt the run before it parked on, and the kernel's own chain says which answer closed it on each path
            issued, yes, no, look = runs[i]['model_receipts'][-1], runs[i + 1], rec['no_runs'][i], rec['no_after'][i]
            closed = lambda r, truth: {'ask': r['scope'] + '|' + issued['ask']['predicate'], 'receipt': issued['sha256'], 'truth': truth, 'source': 'STAMP:' + issued['ask']['to']} in [x['data'] for x in r['trace'] if x['operation'] == 'ASK_CLOSED']
            ok = ok and (issued.get('parked') is True and runs[i]['work_state'] == 'waiting' and closed(yes, 'TRUE') and closed(no, 'FALSE') and (look is not None) == (no['work_state'] == 'completed')
                         and (look is None or look['work_state'] in ('ready', 'blocked')))
        if ok and rec['standard'] is not None:   # the judgement kept exactly the rows of the checklist of the workflow generated from the first look, and its goal is the standard's
            wf, j = generated(plan, books(domain), sha)['workflow'], rec['standard']
            ok = (j['goal'] == standard[0]['goals'][0] == standard[1]['rules'][0]['head'] and all(x['truth'] == 'TRUE' for x in checklist(wf, sha))
                  and same([x['data'] for x in j['trace'] if x['operation'] == 'RETAIN'], [{'predicate': x['predicate'], 'source': x['source'], 'version': x['version']} for x in checklist(wf, sha)]))
        return ok

    def judged(d, i, e, asked, cat, row):   # one recorded system, read once: what holds of it, and the system this file works out for it
        key = (i, e.get('folder'), tuple(sorted(e['files'].items())), id(e.get('looks')), id(d['cases']), id(d['action_handlers']))
        if key in found:   # the looks, the cases and the handlers are kept beside the finding, so the identities in the key stay theirs
            return found[key][3]
        out = {'whole': False, 'record': False, 'system': False, 'page': False, 'domain': False, 's': None}
        files = e['files']

        def holds(test):   # one finding on its own: what cannot be read does not hold
            try:
                return test() is True
            except Exception:
                return False
        out['whole'] = holds(lambda: whole(e, parsed(files['system.json'])))
        try:
            choice = choice_of(asked, cat, row)
            mine = parsed(files['system.json'])
            if choice['domain'] is None:   # nothing was guessed: the draft and the kernel's one look at it are made here from the words (four rows, their hashes, the whole result)
                pack, look = draft_of(asked, sha)
                rec, chosen = {'schema': 'core-algorithm/system-record/1', 'draft': look}, None
                out['record'] = files['record.json'] == dump(rec) and 'looks' not in e
                out['domain'] = holds(lambda: same(mine['choice'], choice) and same(mine['draft']['pack'], pack) and pack['rules'][0]['approved'] is False and 'methods' not in pack
                                      and look['status'] == mine['draft']['kernel_status'] == 'SEMANTICS_UNAPPROVED' and all(k not in mine for k in ('domain', 'plan', 'implementation', 'model_run', 'standard', 'blocked_at')))
            else:   # the domain is a row of the closed list, and its packs are a recorded case: the system's first look, or its first run, is that case's run
                rec, chosen = parsed(files['record.json']), row or [c for c in cat if c['id'] == choice['domain']][0]
                out['record'] = holds(lambda: record_ok(e, rec, chosen))
                roots = [r['trace_root_sha256'] for r in [rec['plan']] + rec['runs'][:1]]
                out['domain'] = holds(lambda: same(mine['choice'], choice) and same(mine['domain'], {k: chosen[k] for k in ('id', 'title', 'goal', 'say', 'packs')})
                                      and any(c['outcome']['trace_root_sha256'] in roots for c in d['cases'] if c['packs'] == chosen['packs'] and c['outcome']))
            s = system_of(asked, cat, row, rec, d['action_handlers'], pk, sha)   # worked out from the results as they stand in record.json, whether or not they agree with their traces: that is S121's to say
            out['s'] = s
            out['system'] = files['system.json'] == dump(s)

            def page_ok():
                style = re.findall(r'<style>(.*?)</style>', files['index.html'], re.S)
                markup = markup_of(files['index.html'].replace('<style>' + style[0] + '</style>', '<style></style>', 1)) if len(style) == 1 else None   # the style sheet is held by its digest
                return (len(style) == 1 and fsha(style[0]) == STYLE_SHA256 and files['index.html'] == page_of(s, rec, style[0]) and markup is not None
                        and markup[0] <= TAGS and {k for _, k, _ in markup[1]} <= ATTRS and all(v == 'radio' for t, k, v in markup[1] if t == 'input' and k == 'type')
                        and all((k, v) in (('charset', 'utf-8'), ('name', 'viewport')) or k == 'content' for t, k, v in markup[1] if t == 'meta')
                        and {v for _, k, v in markup[1] if k == 'href'} == {name for name in s['file_names'] if name != 'index.html'}
                        and all(w not in files['index.html'].lower() for w in ('http', '@import', 'url(', 'javascript:'))
                        and drawn_ok(files['index.html'], s['implementation']['workflow'] if chosen else {'steps': [], 'edges': []}))
            out['page'] = holds(page_ok)
        except Exception:
            pass
        found[key] = (e.get('looks'), d['cases'], d['action_handlers'], out)
        return out

    def command_ok(command, e, s):   # S125: the command wrote the recorded bytes of the first system into one folder, twice the same; a refusal is one line, exit code 2, and writes nothing; a write that could not be reported is one line and exit code 3
        want = {e['folder'] + '/' + name: fsha(t) for name, t in e['files'].items()}
        line = f"{s['verdict']:<10} {s['asked']}  ->  <out>/{e['folder']}/index.html"
        argv = s['asked'].split() + ['--out', '<out>']
        build = lambda x: same([x['exit'], x['stdout'], x['stderr']], [0, [line], []]) and same(x['written'], want)
        return (len(command) == 5 and all(sorted(x) == ['argv', 'exit', 'stderr', 'stdout', 'written'] for x in command)
                and [x['argv'] for x in command] == [argv] * 3 + [['a', 'site', '--domain', 'nobody-reviewed-this', '--out', '<out>'], argv]
                and build(command[0]) and build(command[1])
                and same([command[2]['exit'], command[2]['stdout'], command[2]['stderr']], [2, [], [f"g2.py: error: <out>/{e['folder']} already holds something that is not this system (notes.txt): nothing was written"]])
                and same(command[2]['written'], dict(want, **{e['folder'] + '/notes.txt': fsha('mine')}))
                and same([command[3]['exit'], command[3]['stdout'], command[3]['stderr']], [2, [], ['g2.py: error: Unknown domain: pick one from the catalogue']]) and same(command[3]['written'], command[2]['written'])
                and same([command[4]['exit'], command[4]['stdout'], command[4]['stderr']], [3, [], ['g2.py: error: 1 of 1 folders were written under <out>, and the line that says so could not be printed (BrokenPipeError)']])
                and same(command[4]['written'], want))

    def views_ok(c, pins):   # S126 and S128: what a case says beside its runs (its scope, its run block, its four views, its rule ids) is what its pack files leave, and what its run says beside its trace is this file's own value
        packs = [pk(n) for n in c['packs']]
        b, rows, r = books(packs), stored(packs), c['outcome']
        return (c['scope'] == r['scope'] == b['scope'] and sorted(c['run']) == ['goals', 'runs', 'status'] and same([c['run']['status'], c['run']['goals']], ['EVALUATED', b['goals']])
                and same(c['derived_state']['facts'], rows) and same(c['four_views']['world'], [{'predicate': k, 'truth': x['truth'], 'source': x.get('source')} for k, x in rows.items()])
                and same(c['four_views']['knowledge'], list(b['rules'].values())) and same(c['derived_state']['rule_ids'], [x['id'] for x in b['rules'].values()])
                and same([r['needs'], r['proof'], r['selected_branch'], r['candidates'], r['learning'], r['learning_record']],
                         list(pins) + [[], [], {'source_trace': r['trace_root_sha256'], 'learning_sha256': sha([])}]))   # the run block's copy of the run is this one (S42)

    def case_70_ok(d, e, s):   # S126: case 70 at the kernel waits on the customer with nothing shipped, on the desk's row; the system built from its packs shows what the yes leads to
        c = [x for x in d['cases'] if x['id'] == '70_recorded_open'][0]
        r, rec, desk = c['outcome'], parsed(e['files']['record.json']), c['derived_state']['facts']['orgA/fulfillment|order_complete']
        after = rec['after']
        return (views_ok(c, CASE70_SAYS)
                and same([r['status'], r['work_state'], r['actions'], r['pending'], r['waits'], r['goal_truth_before'], r['goal_truth_after'], r['cost']], ['WAITING', 'waiting', [ASK], [SHIP], [ASK], 'FALSE', 'FALSE', {'compute': 0, 'money': 0, 'attention': 1}])
                and len(r['model_receipts']) == 1 and r['model_receipts'][0].get('parked') is True and r['model_receipts'][0]['ask']['to'] == 'customer'
                and same([desk['truth'], desk['source'], desk['version'], desk.get('final', False)], ['FALSE', 'fixture/order-desk', 'desk-1', False])
                and same(c['derived_state']['budget_after'], {'compute': 10, 'money': 10, 'attention': 2})
                and s['domain']['packs'] == c['packs'] and rec['runs'][0]['trace_root_sha256'] == r['trace_root_sha256']
                and [x['method'] for x in rec['runs'][1]['model_receipts']] == [SHIP] and rec['runs'][1]['status'] == 'LOCAL_MODEL_EFFECTS_RECORDED'
                and after['status'] == 'EVIDENCE_CONFLICT' and {'predicate': 'order_complete'} in [x['data'] for x in after['trace'] if x['operation'] == 'EVIDENCE_CONFLICT']
                and same([rec['no_runs'][0]['status'], rec['no_runs'][0]['work_state'], rec['no_runs'][0]['model_receipts']], ['REFUSED', 'blocked', []])   # a no is final here too: nothing ships
                and s['verdict'] == 'NOT_READY' and same(s['blocked_at'], [{'reason': 'GOAL_NOT_HELD', 'at': ['order_complete'], 'detail': 'EVIDENCE_CONFLICT'}]))

    def case_71_ok(d, e, s):   # S128: case 71 at the kernel waits on the customer with nothing else to run, on the desk's row; after the yes the kernel has no plan left and gives two reasons; the page names the one the kernel names the run with
        c = [x for x in d['cases'] if x['id'] == '71_no_plan_after_a_yes'][0]
        r, rec, desk = c['outcome'], parsed(e['files']['record.json']), c['derived_state']['facts']['orgA/closing|order_closed']
        yes, no = rec['runs'][1], rec['no_runs'][0]
        ops = lambda run: [(x['operation'], x['data'].get('predicate')) for x in run['trace'] if x['operation'] in run['stop_reasons']]
        lead = ('<p class="lead">A plan was found, but it does not get there in the local model, after customer said yes: the kernel has no plan left, because the facts contradict each other '
                '(the order is closed).</p>')
        return (views_ok(c, CASE71_SAYS)
                and same([r['status'], r['work_state'], r['actions'], r['pending'], r['waits'], r['goal_truth_before'], r['goal_truth_after'], r['cost']], ['WAITING', 'waiting', [RECEIPT], [], [RECEIPT], 'FALSE', 'FALSE', {'compute': 0, 'money': 0, 'attention': 1}])
                and len(r['model_receipts']) == 1 and r['model_receipts'][0].get('parked') is True and r['model_receipts'][0]['ask']['to'] == 'customer'
                and same([desk['truth'], desk['source'], desk['version'], desk.get('final', False)], ['FALSE', 'fixture/order-desk', 'desk-1', False])
                and same(c['derived_state']['budget_after'], {'compute': 10, 'money': 10, 'attention': 2})
                and s['domain']['packs'] == c['packs'] == ['173_closed_on_confirmation'] and rec['runs'][0]['trace_root_sha256'] == r['trace_root_sha256'] and len(rec['runs']) == 2
                and same([yes['status'], yes['work_state'], yes['stop_reasons'], yes['model_receipts']], ['EVIDENCE_CONFLICT', 'blocked', ['EVIDENCE_CONFLICT', 'QUERY_EVIDENCE'], []])
                and ops(yes) == [('QUERY_EVIDENCE', 'refund_recorded'), ('EVIDENCE_CONFLICT', 'order_closed')]   # in the order of the trace the unknown refund comes first: the kernel names the run with the conflict
                and same([no['status'], no['work_state'], no['stop_reasons'], no['model_receipts']], ['REFUSED', 'blocked', ['QUERY_EVIDENCE', 'REFUSED'], []])
                and s['verdict'] == 'NOT_READY' and same(s['blocked_at'], [{'reason': 'QUERY_EVIDENCE', 'at': ['refund_recorded'], 'detail': None}, {'reason': 'EVIDENCE_CONFLICT', 'at': ['order_closed'], 'detail': None}])
                and e['files']['index.html'].count(lead) == 1 and e['files']['index.html'].count('<p class="lead">') == 1
                and e['files']['index.html'].count('<div class="panel y"><p><b>The run ends here: the facts contradict each other.</b></p></div>') == 1)

    def claims(d):
        sc, cat, shown = d['scenes']['system'], pk(CATALOGUE)['domains'], pk(EXHIBITS)['domains']
        said = [r['say'] for r in cat] + [NEWS, TIE] + [r['say'] for r in shown]
        n = len(cat) + 2
        if (sc.get('schema') != 'core-algorithm/systems-record/3' or sorted(sc) != ['command', 'schema', 'systems'] or len(sc['systems']) != len(said)
                or any(not {'folder', 'files'} <= set(e) <= {'folder', 'files', 'looks'} for e in sc['systems'])):
            return {}
        each = [judged(d, i, e, said[i], cat if i < n else [shown[i - n]], None if i < n else shown[i - n]) for i, e in enumerate(sc['systems'])]
        got = [x['s'] for x in each]
        failing = lambda key: ', '.join(f'system {i + 1}' for i, x in enumerate(each) if not x[key])   # what a failed row says: which of the ten systems, counted from one
        runs_of = lambda s: s['model_run']['path'] if 'model_run' in s else []

        def holds(test):   # one row on its own: a system this file could not work out fails the rows that read it, and no other
            try:
                return test() is True
            except Exception:
                return False

        def follow():   # S122: every system.json is the text worked out here, and the ten say what the tables above hold
            site, order, tie, closing = got[0], got[1], got[n - 1], got[n + 3]
            return (all(x['system'] for x in each) and [s['verdict'] for s in got] == VERDICTS
                    and same([[[x['method'] for x in r['receipts']] for r in runs_of(s)] if 'model_run' in s else None for s in got], RAN) and same([s.get('blocked_at') for s in got], WAY)
                    and all(not r['skipped'] and all(x['status'] == 'LOCAL_ONLY' for x in r['receipts']) for s in got for r in runs_of(s))   # no step was skipped, and every receipt is local only
                    and [len(s['model_run']['asks']) if 'model_run' in s else None for s in got] == [0, 1, 0, 0, None, None, 0, 0, 1, 1]
                    and all(a['to'] == 'customer' and a['if_no']['status'] == 'REFUSED' and a['if_no']['receipts'] == [] for s in got if 'model_run' in s for a in s['model_run']['asks'])   # every question on record goes to the customer, and a no is final
                    and len(site['implementation']['workflow']['edges']) == 4 and order['model_run']['asks'][0]['if_yes']['status'] == 'LOCAL_MODEL_EFFECTS_RECORDED'
                    and tie['choice']['tied'] == ['order', 'website'] and tie['choice']['domain'] is None   # one word of each of two domains: nothing is chosen
                    and closing['model_run']['path'][-1]['status'] == 'EVIDENCE_CONFLICT')
        return {'notes': {NAMES[0]: failing('whole'), NAMES[1]: failing('record'), NAMES[2]: failing('system'), NAMES[3]: failing('page'), NAMES[4]: failing('domain')},
                NAMES[0]: all(x['whole'] for x in each) and len({e['folder'] for e in sc['systems']}) == len(said), NAMES[1]: all(x['record'] for x in each), NAMES[2]: holds(follow),
                NAMES[3]: all(x['page'] for x in each), NAMES[4]: all(x['domain'] for x in each),
                NAMES[5]: holds(lambda: command_ok(sc['command'], sc['systems'][0], got[0])),
                NAMES[6]: holds(lambda: case_70_ok(d, sc['systems'][n + 2], got[n + 2])),
                NAMES[7]: holds(lambda: case_71_ok(d, sc['systems'][n + 3], got[n + 3]))}

    try:
        honest, fault = claims(data), ''
    except Exception as e:
        honest, fault = {}, repr(e)
    out = [(name, honest.get(name, False) is True, fault or honest.get('notes', {}).get(name, '')) for name in NAMES]
    return out + [forgeries_row(data, ROOT, sha, claims, honest, fault, pk, parsed)]


# ---------------------------------------------------------------- the same claims on forged records
def forgeries_row(data, ROOT, sha, claims, honest, fault, pk, parsed):
    """S127. The claims must fail on a forged record, and each forgery must be refused by the row it is listed for. A forger repairs what a careless edit breaks: every
    digest, manifest and folder name is made to fit again, the page quotes the new digest, the files of a changed workflow or draft are written again, the looks beside
    a changed record.json follow it, and the command's recorded runs name the new folder and digests (reseal). The hardest forger also writes system.json, the part
    files and the page again from the forged results, by this file's own rules (refit). What is left to catch the forgery is the content."""
    S = lambda d: d['scenes']['system']['systems']
    cat, shown = pk(CATALOGUE)['domains'], pk(EXHIBITS)['domains']
    n = len(cat) + 2
    said = [r['say'] for r in cat] + [NEWS, TIE] + [r['say'] for r in shown]

    def copy_of():   # the record, copied as far as a forgery changes it: the list of systems, each entry, its files and the command's runs. The looks, the cases and the handlers are shared: a forgery that changes one of them copies it first
        sc = data['scenes']['system']
        return dict(data, scenes=dict(data['scenes'], system=dict(sc, systems=[dict(e, files=dict(e['files'])) for e in sc['systems']], command=json.loads(json.dumps(sc['command'])))))

    def case(d, cid):   # one case of a copy, itself copied the first time a forgery reaches for it
        if all(c is o for c, o in zip(d['cases'], data['cases'])):
            d['cases'] = list(data['cases'])
        i = [c['id'] for c in d['cases']].index(cid)
        if d['cases'][i] is data['cases'][i]:
            d['cases'][i] = json.loads(json.dumps(data['cases'][i]))
        return d['cases'][i]

    def reseal(d):
        for e in S(d):
            s = dict(parsed(e['files']['system.json']))   # a copy of the top level: only the digest is set anew
            old = s['system_sha256']
            s['system_sha256'] = sha({k: v for k, v in s.items() if k != 'system_sha256'})
            if s['system_sha256'] != old:
                e['files']['index.html'] = e['files']['index.html'].replace(old, s['system_sha256'])
                e['files']['system.json'] = dump(s)
            e['files']['manifest.json'] = manifest_of(e['files'], s['system_sha256'])
            e['folder'] = e['folder'][:-16] + fsha(e['files']['manifest.json'])[:16]
        first = S(d)[0]
        want = {first['folder'] + '/' + name: fsha(t) for name, t in first['files'].items()}
        for i, x in enumerate(d['scenes']['system']['command']):
            x['written'] = dict(want) if i in (0, 1, 4) else dict(want, **{first['folder'] + '/notes.txt': fsha('mine')})
            x['stdout'] = [line[:line.index('<out>/')] + '<out>/' + first['folder'] + '/index.html' for line in x['stdout']]
            x['stderr'] = [line if '<out>/' not in line else 'g2.py: error: <out>/' + first['folder'] + line[line.index(' already holds'):] for line in x['stderr']]
        return d

    def forged(target, change, seal=True):   # None when the forgery is refused by the row it is listed for; else why it counts as missed
        d = copy_of()
        try:
            change(d)
            if seal:
                reseal(d)
        except Exception as e:
            return 'could not be made (' + type(e).__name__ + ')'
        try:
            got = claims(d)
        except Exception:
            return None   # a record so forged that the claims cannot be read fails every row
        return None if got.get(target, False) is not True else ('passes every row' if all(got.get(name, False) is True for name in NAMES) else 'is not refused by ' + target[:4])

    def Y(i, change):   # system.json of system i, changed; the files of its workflow, atoms, scaffold or draft pack are written again from it
        def go(d):
            e = S(d)[i]
            s = json.loads(e['files']['system.json'])
            change(s)
            e['files']['system.json'] = dump(s)
            if 'implementation' in s:
                e['files'].update({'workflow.json': dump(s['implementation']['workflow']), 'atoms.json': dump(s['implementation']['atoms']), 'scaffold.json': dump(s['implementation']['scaffold'])})
            if 'draft' in s:
                e['files']['draft-pack.json'] = dump(s['draft']['pack'])
        return go

    def refit(d, i):   # the hardest forger: system.json, the part files and the page of system i written again from its record.json by this file's own rules; left as they are when this file has no words for the forged results
        e = S(d)[i]
        try:
            rec = json.loads(e['files']['record.json'])
            s = system_of(said[i], cat if i < n else [shown[i - n]], None if i < n else shown[i - n], rec, d['action_handlers'], pk, sha)
            page = page_of(s, rec, re.findall(r'<style>(.*?)</style>', e['files']['index.html'], re.S)[0])
        except Exception:
            return
        e['files'].update({'system.json': dump(s), 'index.html': page})
        if 'implementation' in s:
            e['files'].update({'workflow.json': dump(s['implementation']['workflow']), 'atoms.json': dump(s['implementation']['atoms']), 'scaffold.json': dump(s['implementation']['scaffold'])})

    def rj(i, change, fit=False):   # record.json of system i, changed; the looks kept beside it follow; with fit, everything said about it is written again
        def go(d):
            e = S(d)[i]
            rec = json.loads(e['files']['record.json'])
            change(rec)
            e['files']['record.json'] = dump(rec)
            if 'looks' in e:
                try:
                    e['looks'] = {'runs': json.loads(json.dumps(looks_of(rec)))}
                except Exception:
                    pass   # a record so changed that its looks cannot be listed keeps the old ones beside it
            if fit:
                refit(d, i)
        return go

    def swap(i, old, new, name='index.html'):   # one text of one file of system i replaced, once; the text must be there
        def go(d):
            t = S(d)[i]['files'][name]
            if old not in t:
                raise KeyError(old)
            S(d)[i]['files'][name] = t.replace(old, new, 1)
        return go

    def cut(i, pattern, make, name='index.html'):   # the first match of a pattern in one file of system i replaced by what `make` gives for it; the pattern must be there
        def go(d):
            t = S(d)[i]['files'][name]
            m = re.search(pattern, t, re.S)
            if not m:
                raise KeyError(pattern)
            S(d)[i]['files'][name] = t[:m.start()] + make(m.group(0)) + t[m.end():]
        return go

    def rehash(r):   # one look or run with its receipts and its chain hashed again, as a forger would after changing it
        prev = 'GENESIS'
        for k, row in enumerate(r['trace']):
            if row['operation'] == 'LOCAL_EFFECT':
                row['data']['receipt']['sha256'] = sha({x: y for x, y in row['data']['receipt'].items() if x != 'sha256'})
            row.update(seq=k + 1, prev_sha256=prev)
            row['sha256'] = prev = sha({x: y for x, y in row.items() if x != 'sha256'})
        r['model_receipts'] = [row['data']['receipt'] for row in r['trace'] if row['operation'] == 'LOCAL_EFFECT']
        r['trace_root_sha256'] = prev

    def rechain(i, pick, change):   # one look or run of system i changed and hashed again, and everything said about it written again from the forged record
        return rj(i, lambda rec: (change(pick(rec)), rehash(pick(rec))), fit=True)

    def replanned(i):   # the first look and the first run of system i re-made alike (the look still opens the run's chain), and everything said about them written again
        change = lambda r: (r['trace'][1]['data'].update(alternatives=r['trace'][1]['data']['alternatives'] + 1), rehash(r))
        return rj(i, lambda rec: (change(rec['plan']), change(rec['runs'][0])), fit=True)

    def reroute(rec):   # the order system's yes run re-made as a run of another step than the plan shows, whole: the run, its receipts, what it cost and its chain
        run = json.loads(json.dumps(rec['runs'][1]).replace(SHIP, 'ship-original@1'))
        cost = {dim: pk('02_methods')['methods'][0]['cost'].get(dim, 0) for dim in run['cost']}
        run['cost'] = cost
        [e['data'].update(full_cost=cost) for e in run['trace'] if e['operation'] == 'SELECT']
        rehash(run)
        rec['runs'][1] = run

    def lifted(d):   # the round-two fault as the hardest forgery: the order the desk recorded as open re-made, whole, as a system that waits. Its last look is told as one
        # that finds the goal held, a judgement of its own workflow is put beside it (the order system's, its kept rows re-versioned), and system.json, the part files and the page follow
        donor = json.loads(json.dumps(parsed(S(d)[1]['files']['record.json'])['standard']))

        def change(rec):
            wf, zero = generated(rec['plan'], books([pk(name) for name in shown[2]['packs']]), sha)['workflow'], {dim: 0 for dim in rec['plan']['cost']}
            after = rec['after']
            after.update(status='PLAN_READY', work_state='ready', stop_reasons=[], actions=[], cost=zero, pareto_options=1)
            after['trace'][1:] = [dict(after['trace'][1], operation='SELECT', data={'actions': [], 'full_cost': zero, 'pareto_options': 1}), dict(after['trace'][-1], data={'status': 'PLAN_READY', 'work_state': 'ready'})]
            rehash(after)
            [e['data'].update(version='wf-' + sha(wf)[:12]) for e in donor['trace'] if e['operation'] == 'RETAIN']
            rehash(donor)
            rec['standard'] = donor
        rj(OPENED, change, fit=True)(d)

    def skip_first(r):   # the first step of a run told as already true at its turn: its receipt taken out, one row in its place, what ran and what it cost told anew
        k = next(j for j, e in enumerate(r['trace']) if e['operation'] == 'LOCAL_EFFECT')
        mid, table = r['trace'][k]['data']['receipt']['method'], {m['id']: m for p in r['provenance'] for m in pk(p['pack']).get('methods', [])}
        r['trace'][k] = dict(r['trace'][k], operation='STEP_ALREADY_TRUE', data={'method': mid, 'effect': table[mid]['effect'], 'source': 'LOCAL_MODEL:' + mid, 'version': 'local-sim-1'})
        r.update(actions=[a for a in r['actions'] if a != mid], skipped=[mid])
        r['cost'] = {dim: sum(table[a].get('cost', {}).get(dim, 0) for a in r['actions']) for dim in r['cost']}

    def several(*changes):
        def go(d):
            for change in changes:
                change(d)
        return go

    hide = lambda inner: '<div class="choice"><div class="panel">' + inner + '</div></div>'   # the page's own style sheet shows no .choice .panel
    PICTURE, QUESTION = r'<div class="scroll"><svg class="plan".*?</svg></div>', r'<h2>Waiting on an answer</h2>.*?present the receipt of this question\.</p>'
    W = lambda s: s['implementation']['workflow']
    R = lambda s: s['model_run']
    A = lambda s: s['model_run']['asks'][0]
    SYSTEM, RECORD, PAGE, WHOLE, DOMAIN, COMMAND, CASE70, CASE71 = NAMES[2], NAMES[1], NAMES[3], NAMES[0], NAMES[4], NAMES[5], NAMES[6], NAMES[7]
    BLOCKED, STOP, OPENED, CLOSING = n, n + 1, n + 2, n + 3   # the four exhibits, by their place among the systems
    NOT_THERE = ('A plan was found, but it does not get there in the local model, after customer said yes: every step ran, and afterwards it still does not hold that the order is complete '
                 '(the facts contradict each other).')
    WAITS = 'Waiting on customer: one question has to be answered before the rest of the 2 steps can run.'
    CHOSEN = 'chosen by a word match on organisation, website (a stand-in: a person or an agent should confirm the choice).'
    NO_PLAN = 'the kernel has no plan left, because the facts contradict each other (the order is closed).'
    sealed = [
     # ---- what the system says: the plan, the choice, the domain, the packs, the standard (each alone in system.json, every digest made to fit)
     (SYSTEM, Y(0, lambda s: s['plan'].update(status='METHOD_ABSENT'))), (SYSTEM, Y(0, lambda s: s['plan'].update(actions=[]))), (SYSTEM, Y(0, lambda s: s.pop('plan'))),
     (SYSTEM, Y(0, lambda s: s['plan'].update(proof=['approved by the board']))),   # a field the system does not carry: what a result says beside its trace is on no system
     (SYSTEM, Y(0, lambda s: s['choice'].update(how='the caller'))), (SYSTEM, Y(0, lambda s: s['choice'].update(domain='order'))), (SYSTEM, Y(0, lambda s: s['choice']['ranking'].reverse())),
     (SYSTEM, Y(0, lambda s: s['domain'].update(title='Shop'))), (SYSTEM, Y(0, lambda s: s['domain'].update(packs=['00_goal']))), (SYSTEM, Y(0, lambda s: s['labels'].update(site_live='the shop is open'))),
     (SYSTEM, Y(0, lambda s: s['pack_digests']['domain'][2].update(sha256='0' * 64))), (SYSTEM, Y(0, lambda s: s['pack_digests']['standard'].pop())), (SYSTEM, Y(1, lambda s: s.pop('pack_digests'))),
     (SYSTEM, Y(0, lambda s: s['standard'].update(status='METHOD_ABSENT'))), (SYSTEM, Y(0, lambda s: s['standard']['checks'][0].update(truth='FALSE'))), (SYSTEM, Y(0, lambda s: s['standard'].update(workflow='W-other'))),
     (SYSTEM, Y(0, lambda s: s['standard'].update(registrable=False))), (SYSTEM, Y(0, lambda s: s['standard']['evidence'][1].update(version='wf-000000000000'))), (SYSTEM, Y(0, lambda s: s['standard'].update(rule='R-OTHER@1'))),
     (SYSTEM, Y(0, lambda s: [x.update(question='the workflow was approved by the board') for x in s['standard']['checks'][:1] + s['standard']['evidence'][:1]])),   # the question of a check, changed in both places
     # ---- the run in the local model
     (SYSTEM, Y(0, lambda s: R(s)['path'][0].update(stopped={'method': 'check-site@1', 'reason': 'x'}))), (SYSTEM, Y(0, lambda s: R(s)['path'][0]['receipts'][0].update(sha256='0' * 64))),
     (SYSTEM, Y(0, lambda s: R(s)['path'][0]['receipts'][0].update(method='check-site@1'))), (SYSTEM, Y(0, lambda s: R(s)['path'][0].update(receipts=[]))), (SYSTEM, Y(0, lambda s: R(s)['path'][0]['receipts'][0].update(status='EXTERNAL'))),
     (SYSTEM, Y(0, lambda s: R(s).update(goal_held=False))), (SYSTEM, Y(0, lambda s: R(s).update(effects_missing=['check-site@1']))), (SYSTEM, Y(0, lambda s: R(s)['after'].update(status='WAITING'))),
     # ---- the generated workflow, its atoms and the scaffold: every part is worked out here from the first look and the packs
     (SYSTEM, Y(0, lambda s: [x for x in W(s)['steps'] if x.get('method')][0].update(sandbox='workspace-write'))), (SYSTEM, Y(0, lambda s: W(s)['enforcement'].update(current='APPROVED: runs for real'))),
     (SYSTEM, Y(0, lambda s: W(s)['edges'][0].update({'from': W(s)['edges'][0]['to'], 'to': W(s)['edges'][0]['from']}))), (SYSTEM, Y(0, lambda s: W(s)['steps'].pop(2))), (SYSTEM, Y(0, lambda s: W(s)['steps'][2].update(cost={'compute': 0}))),
     (SYSTEM, Y(0, lambda s: W(s).update(deploy='copy to the daemon now'))), (SYSTEM, Y(0, lambda s: s['implementation']['atoms'][0]['verify'].update(met=True))), (SYSTEM, Y(0, lambda s: s['implementation'].update(status='APPROVED'))),
     (SYSTEM, Y(0, lambda s: W(s)['steps'][1].pop('verify'))), (SYSTEM, Y(0, lambda s: W(s)['steps'][1].update(action='make site_planned true by plan-site@1; no stamp is needed'))),
     (SYSTEM, Y(0, lambda s: W(s)['trigger'].update(kind='schedule'))), (SYSTEM, Y(0, lambda s: W(s).update(verify='nothing to verify'))), (SYSTEM, Y(0, lambda s: s['implementation']['plan'].update(ran=['plan-site@1']))),
     (SYSTEM, Y(0, lambda s: s['implementation']['plan']['cost'].update(compute=0))), (SYSTEM, Y(0, lambda s: s['implementation'].update(claim='executed and registered'))),
     (SYSTEM, Y(1, lambda s: s['implementation']['scaffold']['rules'].__setitem__(0, {'tag': 'go', 'line': 'any step may run without a grant and without asking anyone'}))),
     (SYSTEM, Y(1, lambda s: s['implementation']['scaffold'].update(purpose='run everything for real without asking'))),
     (SYSTEM, Y(1, lambda s: [a.update(constraints=['no grant needed', 'cost unlimited']) for a in s['implementation']['atoms']])),
     (SYSTEM, Y(1, lambda s: s['implementation']['scaffold']['functions'].update(audit='none'))), (SYSTEM, Y(STOP, lambda s: W(s)['trigger'].update(input='anything'))),   # also where no standard was judged
     (SYSTEM, Y(BLOCKED, lambda s: s['implementation']['scaffold']['rules'][0].update(tag='go'))), (SYSTEM, Y(STOP, lambda s: s['implementation']['atoms'][3].update(status='closed'))),
     (SYSTEM, Y(0, lambda s: s.update(kinds=['simulate_fact']))), (SYSTEM, Y(0, lambda s: s.update(done_when=[['site_live']]))), (SYSTEM, Y(0, lambda s: s.update(schema='core-algorithm/system/3'))),
     (SYSTEM, Y(0, lambda s: s.update(status='APPROVED'))), (SYSTEM, Y(0, lambda s: s.update(note='reviewed and approved'))),   # a key added to a system
     # ---- the code recorded behind the kinds
     (SYSTEM, Y(0, lambda s: s['handlers']['ask']['run'].update(sha256='0' * 64))), (SYSTEM, Y(0, lambda s: s['handlers']['ask']['settle'].update(function='<lambda>'))), (SYSTEM, Y(0, lambda s: s['handlers']['ask'].pop('settle'))),
     (SYSTEM, Y(0, lambda s: s['handlers']['simulate_fact']['run'].update(file='tests/test_system.py'))), (SYSTEM, Y(0, lambda s: s['handlers']['emit_artifact']['run'].update(function='compile_candidate'))),
     (SYSTEM, Y(0, lambda s: s['handlers']['simulate_fact'].update(plan=dict(s['handlers']['simulate_fact']['run'])))), (SYSTEM, Y(0, lambda s: s['handlers'].pop('emit_artifact'))),
     # ---- the verdict and the rows that say what stands in the way
     (SYSTEM, Y(0, lambda s: s.update(verdict='WAITING'))), (SYSTEM, Y(1, lambda s: s.update(verdict='READY'))), (SYSTEM, Y(3, lambda s: s.update(verdict='NOT_READY'))),
     (SYSTEM, Y(OPENED, lambda s: s.update(verdict='WAITING', blocked_at=[]))), (SYSTEM, Y(STOP, lambda s: s.update(verdict='READY', blocked_at=[]))), (SYSTEM, Y(CLOSING, lambda s: s.update(verdict='WAITING', blocked_at=[]))),
     (SYSTEM, Y(BLOCKED, lambda s: s.update(verdict='READY', blocked_at=[]))), (SYSTEM, Y(OPENED, lambda s: s['blocked_at'][0].update(detail='PLAN_READY'))),
     (SYSTEM, Y(STOP, lambda s: s['blocked_at'][0].update(detail='Handler refused: try again later'))), (SYSTEM, Y(STOP, lambda s: s['blocked_at'][0].update(at=['read-component@1']))), (SYSTEM, Y(BLOCKED, lambda s: s['blocked_at'].pop(0))),
     (SYSTEM, Y(BLOCKED, lambda s: s['blocked_at'][1].update(at=['substitute_stock']))), (SYSTEM, Y(OPENED, lambda s: R(s).update(goal_held=True))), (SYSTEM, Y(OPENED, lambda s: R(s)['after'].update(status='PLAN_READY'))),
     (SYSTEM, Y(OPENED, lambda s: s['blocked_at'].insert(0, {'reason': 'ROUTE_CHANGED', 'at': [SHIP], 'detail': None}))), (SYSTEM, Y(CLOSING, lambda s: s['blocked_at'].reverse())), (SYSTEM, Y(CLOSING, lambda s: s['blocked_at'].pop())),
     # ---- the question and both answers
     (SYSTEM, Y(1, lambda s: A(s).update(question='May we charge the card again?'))), (SYSTEM, Y(1, lambda s: A(s).update(asked_by=SHIP))), (SYSTEM, Y(1, lambda s: A(s).update(receipt_sha256='0' * 64))),
     (SYSTEM, Y(1, lambda s: A(s).update(fact='substitute_stock'))), (SYSTEM, Y(1, lambda s: A(s).update(to='mallory'))), (SYSTEM, Y(1, lambda s: A(s)['if_no'].update(status='LOCAL_MODEL_EFFECTS_RECORDED'))),
     (SYSTEM, Y(1, lambda s: A(s)['if_no'].update(goal_held=True))), (SYSTEM, Y(1, lambda s: A(s)['if_yes'].update(pending=[SHIP]))), (SYSTEM, Y(1, lambda s: R(s)['path'][0].update(status='LOCAL_MODEL_EFFECTS_RECORDED'))),
     (SYSTEM, Y(1, lambda s: R(s)['path'][0].update(pending=[]))), (SYSTEM, Y(1, lambda s: s['plan'].update(cost={'compute': 0, 'money': 0, 'attention': 0}))), (SYSTEM, Y(1, lambda s: R(s).update(asks=[]))),
     (SYSTEM, Y(2, lambda s: R(s)['asks'].append({'fact': 'x', 'question': 'x', 'to': 'x', 'asked_by': 'x', 'receipt_sha256': 'x', 'if_yes': R(s)['path'][0], 'if_no': dict(R(s)['path'][0], goal_held=None)}))),
     (SYSTEM, Y(CLOSING, lambda s: A(s)['if_yes'].update(status='QUERY_EVIDENCE'))),
     # ---- the system without a domain, and the tie
     (SYSTEM, Y(4, lambda s: s['draft']['pack']['rules'][0].update(approved=True))), (SYSTEM, Y(4, lambda s: s['draft']['pack'].update(methods=[{'id': 'm', 'effect': s['draft']['pack']['goals'][0]}]))),
     (SYSTEM, Y(4, lambda s: s['draft'].update(trace_root_sha256='0' * 64))), (SYSTEM, Y(4, lambda s: s['draft'].update(kernel_status='PLAN_READY'))), (SYSTEM, Y(4, lambda s: s.update(catalogue=[]))),
     (SYSTEM, Y(4, lambda s: s['choice']['ranking'].pop())), (SYSTEM, Y(4, lambda s: s['draft'].update(to_write=[]))), (SYSTEM, Y(4, lambda s: s['choice'].update(domain='website'))), (SYSTEM, Y(4, lambda s: s.update(verdict='READY'))),
     (SYSTEM, Y(4, lambda s: s['draft']['to_write'].__setitem__(5, 'Nobody has to approve the rules.'))), (SYSTEM, Y(5, lambda s: s['choice'].update(tied=['website']))),
     (SYSTEM, Y(5, lambda s: s['choice'].update(domain='website', tied=[], how='a word match on website (a stand-in: a person or an agent should confirm the choice)'))),   # the tie told as a choice
     # ---- the record beside the page (record.json and the looks beside it; system.json and the page left as they were)
     (RECORD, rj(0, lambda rec: rec['plan']['trace'][2].update(operation='FORGED'))), (RECORD, rj(0, lambda rec: rec['runs'][0].update(claim='EXTERNALLY VERIFIED SUCCESS'))), (RECORD, rj(0, lambda rec: rec.pop('plan'))),
     (RECORD, rj(0, lambda rec: rec.update(after=None))), (SYSTEM, rj(0, lambda rec: rec.update(standard=None))), (RECORD, rj(0, lambda rec: rec['plan'].update(provenance=[]))),
     (RECORD, rj(0, lambda rec: rec['standard']['provenance'].append({'pack': 'evidence', 'sha256': '0' * 64}))), (RECORD, rj(0, lambda rec: rec['runs'][0].update(status='SUPPORTED_BY_EVIDENCE'))),
     (RECORD, rj(0, lambda rec: rec['runs'][0]['model_receipts'][0].update(status='EXTERNAL'))), (RECORD, rj(1, lambda rec: rec['runs'][0].update(work_state='completed'))),
     (RECORD, rj(1, lambda rec: rec['no_runs'].pop())), (RECORD, rj(1, lambda rec: rec['runs'].reverse())), (RECORD, rj(0, lambda rec: rec['plan'].update(note='reviewed'))),   # a key added to a result
     (RECORD, rj(0, lambda rec: rec['runs'][0].update(cost={'compute': 0, 'money': 0, 'attention': 0}), fit=True)),   # a run that cost nothing, with everything said about it written again
     (RECORD, rj(4, lambda rec: rec['draft'].update(status='PLAN_READY'))), (RECORD, rj(4, lambda rec: rec['draft'].update(goal_truth_before='TRUE'))), (RECORD, rj(5, lambda rec: rec['draft']['trace'].pop(1))),
     (RECORD, lambda d: S(d)[4].update(looks={'runs': []})), (RECORD, lambda d: S(d)[0].pop('looks')), (RECORD, lambda d: S(d)[0].update(looks={'runs': S(d)[0]['looks']['runs'][:-1]})),
     (RECORD, lambda d: S(d)[0].update(looks={'runs': S(d)[0]['looks']['runs'][::-1]})), (RECORD, lambda d: S(d)[0].update(looks=dict(S(d)[0]['looks'], more=[]))),
     (RECORD, lambda d: S(d)[1].update(looks={'runs': [dict(r, status='LOCAL_MODEL_EFFECTS_RECORDED') if i == 1 else r for i, r in enumerate(S(d)[1]['looks']['runs'])]})),   # a look kept beside the files that is not the one in record.json
     # ---- the hardest forger: a result re-made with its chain, and system.json, the part files and the page written again from it by this file's own rules
     (DOMAIN, replanned(0)), (DOMAIN, replanned(1)), (DOMAIN, replanned(CLOSING)),   # a first look and a first run rewritten alike and whole: their roots are no longer the recorded case's
     (RECORD, rechain(1, lambda rec: rec['plan'], lambda r: r['trace'][1]['data'].update(alternatives=3))),   # the first look alone: it no longer opens the first run's chain
     (RECORD, rechain(0, lambda rec: rec['standard'], lambda r: [e['data'].update(version='wf-000000000000') for e in r['trace'] if e['operation'] == 'RETAIN'])),   # a judgement of another workflow
     (SYSTEM, rechain(0, lambda rec: rec['runs'][0], skip_first)),   # a run that is no recorded case's, re-made as one that skipped a step: every row holds but the table of what ran
     (SYSTEM, rj(1, reroute, fit=True)),   # the steps that ran are not the steps of the plan the page shows: this file has no words for such a system, and the one on record still says waiting
     (RECORD, several(rj(1, lambda rec: (rec['no_runs'].__setitem__(0, rec['runs'][1]), rec['no_after'].__setitem__(0, rec['after'])), fit=True))),   # the yes run told as what a no leads to: the chain says which answer closed the question
     (SYSTEM, lifted),   # the list of verdicts and the table of what stands in the way say this system is not waiting
     (CASE71, rechain(CLOSING, lambda rec: rec['runs'][1], lambda r: (r.update(status='QUERY_EVIDENCE'), [e['data'].update(reason='QUERY_EVIDENCE') for e in r['trace'] if e['operation'] == 'BLOCK'],
                                                                      r['trace'][-1]['data'].update(status='QUERY_EVIDENCE')))),   # the run after the yes re-made as one the kernel names with the unknown refund: the page then names the refund, and case 71's row holds the reason on record
     # ---- the list of systems, the files, the folder
     (WHOLE, lambda d: S(d).pop()), (WHOLE, lambda d: S(d).__setitem__(0, S(d)[2])), (WHOLE, lambda d: d['scenes']['system'].update(schema='core-algorithm/systems-record/2')), (WHOLE, lambda d: d['scenes']['system'].update(more=[])),
     (WHOLE, lambda d: S(d)[0].update(note='x')), (WHOLE, Y(0, lambda s: s['file_names'].append('extra.json'))),
     (WHOLE, several(Y(0, lambda s: s['file_names'].append('notes.txt')), lambda d: S(d)[0]['files'].update({'notes.txt': 'mine'}))),
     (WHOLE, several(Y(0, lambda s: s['file_names'].__setitem__(2, 'W-site-live.json')), lambda d: S(d)[0]['files'].update({'W-site-live.json': S(d)[0]['files'].pop('workflow.json')}),
                     swap(0, 'href="workflow.json">workflow.json', 'href="W-site-live.json">W-site-live.json'))),   # a file named after the goal: the names are a closed list
     (WHOLE, lambda d: S(d)[0]['files'].pop('atoms.json')), (WHOLE, swap(0, '"open"', '"closed"', 'atoms.json')), (WHOLE, swap(0, 'PROPOSED_ONLY', 'APPROVED', 'workflow.json')), (WHOLE, swap(0, '"go"', '"always"', 'scaffold.json')),
     (WHOLE, swap(4, '"approved": false', '"approved": true', 'draft-pack.json')), (WHOLE, lambda d: S(d)[0].update(folder='another-name-' + S(d)[0]['folder'][-16:])),
     # ---- the page: its words
     (PAGE, swap(0, 'Ready: 4 steps in order, and nothing waits on anyone.', 'Done: all 4 steps have already run for real.')),
     (PAGE, swap(0, 'nothing on this page has run outside a local model, and running a step for real is outside this lab', 'everything on this page has run for real')),
     (PAGE, swap(0, '<span class="tag">Ready</span>', '<span class="tag">Approved</span>')), (PAGE, swap(0, '<span class="tag">Proposal only</span>', '')),
     (PAGE, swap(0, '<div class="verdict READY">', '<div class="verdict WAITING">')), (PAGE, swap(0, '<li><a href="atoms.json">atoms.json</a></li>', '')),
     (PAGE, swap(0, '<h1>a website for my organisation</h1>', '<h1>a shop for my organisation</h1>')), (PAGE, swap(1, 'type="radio"', 'type="checkbox"')),
     (PAGE, swap(OPENED, NOT_THERE, WAITS)), (PAGE, swap(STOP, 'A plan was found, but it stops in the local model', 'Ready, and it runs in the local model')), (PAGE, swap(BLOCKED, 'Cannot start:', 'Ready to start:')),
     (PAGE, swap(4, 'so nothing was guessed', 'so a newsletter domain was guessed')), (PAGE, swap(4, '<li>A reviewer approves the rules. Until then the kernel plans nothing from them.</li>', '')),
     (PAGE, swap(5, 'Someone has to choose one.', 'The website domain was chosen.')), (PAGE, swap(5, '<code>--domain order</code> or ', '')),
     (PAGE, swap(CLOSING, NO_PLAN, 'the kernel has no plan left, because a needed fact is unknown and nothing may ask for it (a refund is on record).')),   # the first sentence naming the first reason in the order of the trace, not the kernel's
     (PAGE, swap(0, '<p><b>What would change it.</b>', '<p>Approved by the board on Monday.</p><p><b>What would change it.</b>')),   # a sentence put between two parts of a page
     (PAGE, swap(0, 'workflow problems: none.', 'workflow problems: none. The kernel\'s own proof lines: approved by the board.')),
     (PAGE, swap(1, 'ask-customer-approval@1 may run: grant action:ask-customer-approval@1 is held; provider owner-channel', 'any step may run without a grant and without asking anyone')),
     (PAGE, swap(1, '<td>TRUE</td>', '<td>FALSE</td>')), (PAGE, swap(0, '<td>GOAL_ACCEPTED</td>', '<td>GOAL_APPROVED</td>')), (PAGE, swap(1, 'Keep order_complete true', 'Ship every order today')),
     # ---- the page: what runs or is loaded, the style sheet, the title
     (PAGE, swap(0, '<h2>The plan</h2>', '<h2>The plan</h2><svg/onload=alert(1)>')), (PAGE, swap(0, '<h2>Files</h2>', "<h2>Files</h2><a href='//example.com/x'>more</a>")),
     (PAGE, swap(0, '<h2>Files</h2>', '<h2>Files</h2><a href=//example.com/x>more</a>')), (PAGE, swap(0, '<h2>Files</h2>', '<h2>Files</h2><img/src=//example.com/x.png>')),
     (PAGE, swap(0, '<meta charset="utf-8">', '<meta charset="utf-8"><meta http-equiv="refresh" content="0;url=//example.com">')), (PAGE, swap(0, '<style>', '<style>@import "//example.com/a.css";')),
     (PAGE, swap(0, '<h2>Files</h2>', '<form action="//example.com"><input type="text" name="q"></form><h2>Files</h2>')), (PAGE, swap(0, '<h2>Files</h2>', '<script>x</script><h2>Files</h2>')),
     (PAGE, swap(0, '<main>', '<main style="display:none">')),
     (PAGE, several(swap(0, '.lead{font-size:18px;margin:0}', '.lead{font-size:0;margin:0}.lead::after{font-size:18px;content:"Done: all 4 steps have run for real."}'), swap(0, '.tag{display:inline-block;', '.tag{display:none;'))),
     (PAGE, several(swap(OPENED, '.tag{display:inline-block;', '.tag{display:none;'), swap(OPENED, '.verdict{border-left:4px solid var(--accent);', '.verdict{display:none;border-left:4px solid var(--accent);'))),
     (PAGE, swap(0, '.tag{display:inline-block;', '.tag{display:none;')), (PAGE, swap(0, '</style>', '</style><style>.tag{display:none}</style>')), (PAGE, swap(0, '</main>', '</main><style>.lead{display:none}</style>')),
     (PAGE, swap(0, '<title>a website for my organisation</title>', '<title>APPROVED AND LIVE</title>')), (PAGE, swap(0, '<title>', '<title>APPROVED AND LIVE</title><title>')),
     # ---- the page: a part wrapped into what the page's own style sheet hides, commented out, or folded away
     (PAGE, swap(0, '<p><span class="tag">Proposal only</span>', '<fieldset class="choice"><div class="panel"><p><span class="tag">Proposal only</span>')),
     (PAGE, swap(0, '<div class="verdict READY">', '<fieldset class="choice"><div class="panel"><div class="verdict READY">')), (PAGE, swap(0, '<footer>', '<fieldset class="choice"><div class="panel"><footer>')),
     (PAGE, swap(0, '</footer>', '</footer><p>Approved and live.</p>')),
     (PAGE, cut(1, PICTURE, lambda m: '<p>Approved: both steps have run and the replacement is on its way.</p>' + hide(m))), (PAGE, cut(1, QUESTION, hide)), (PAGE, cut(0, PICTURE, hide)),
     (PAGE, swap(0, '<h2>The plan</h2>', '<h2>The plan</h2><!-- -- >')), (PAGE, swap(0, '<footer>', '<!-- -- ><footer>')), (PAGE, cut(0, PICTURE, lambda m: '<!--' + m + '-->')),
     (PAGE, swap(0, '<footer>', '<details><summary>more</summary><table><tr><td></details></td></tr></table><footer>')),   # an end tag a browser ignores: the footer in a folded part
     (PAGE, swap(OPENED, '<h2>What stands in the way</h2>', '<div class="verdict READY"><p>Ready: 2 steps in order, and nothing waits on anyone.</p></div><h2>What stands in the way</h2>')),   # a second verdict box
     (PAGE, swap(0, '<h2>Files</h2>', '<fieldset class="choice"><legend>Approved</legend></fieldset><h2>Files</h2>')),
     # ---- the picture: the mark on a box, its words, the place of a box, the ends of an arrow, anything else drawn into it
     (PAGE, swap(STOP, '<g class="stop">', '<g class="">')), (PAGE, swap(STOP, '>stops here</text>', '>runs here</text>')), (PAGE, swap(1, '<g class="later">', '<g class="">')),
     (PAGE, swap(1, '>Ship the replacement</text>', '>Refund the customer</text>')), (PAGE, swap(STOP, '>Construct the candidate</text>', '>Validate the field</text>')), (PAGE, swap(0, '>Plan the site</text>', '>Delete the site</text>')),
     (PAGE, several(swap(0, '>Plan the site</text>', '>\x00</text>'), swap(0, '>Check the site</text>', '>Plan the site</text>'), swap(0, '>\x00</text>', '>Check the site</text>'))),   # the words of the first and the last box exchanged
     (PAGE, swap(0, 'L187,7 L492,7 L492,24"/><polygon class="head" points="492,30 488,23 496,23"', 'L187,7 L706,7 L706,24"/><polygon class="head" points="706,30 702,23 710,23"')),   # the long arrow pointed at another box
     (PAGE, swap(0, 'd="M175,58 L209,58"/><polygon class="head" points="215,58 208,54 208,62"', 'd="M175,8 L209,8"/><polygon class="head" points="215,8 208,4 208,12"')),   # an arrow moved into empty space
     (PAGE, cut(0, r'<svg class="plan"[^>]*>', lambda m: m + '<text x="20" y="12">Approved and live</text>')),   # free text inside the picture
     (PAGE, swap(0, '<rect x="1" y="30"', '<rect x="100" y="30"')), (PAGE, cut(0, r'<path class="edge"[^>]*/><polygon[^>]*/>', lambda m: '')),
     (PAGE, swap(0, '<title>plan-site@1 makes site_planned</title>', '<title>check-site@1 makes site_checked</title>')),
     # ---- the question on a page
     (PAGE, swap(1, '<b>Customer</b> is asked:', '<b>Supplier</b> is asked:')), (PAGE, swap(1, '<b>The plan runs through in the local model.</b>', '<b>The plan has run for real.</b>')),
     (PAGE, swap(1, '<div class="panel n"><p><b>The run ends here: a decision stands against it, and no method may overturn that.</b></p></div>',
                 '<div class="panel n"><p><b>The plan runs through in the local model.</b> Ran in the local model: Ship the replacement.</p></div>')),
     (PAGE, swap(OPENED, '<b>Every step runs, and afterwards the goal still does not hold.</b>', '<b>The plan runs through in the local model.</b>')),
     (PAGE, swap(CLOSING, '<div class="panel y"><p><b>The run ends here: the facts contradict each other.</b></p></div>', '<div class="panel y"><p><b>With this answer the goal holds; no step is left to run.</b></p></div>')),
     (PAGE, swap(1, 'The answer must come from customer and present the receipt of this question.', 'Anyone may answer.')),
     # ---- who chose the domain, said before the plan
     (PAGE, swap(0, CHOSEN + '</p><h2>The plan</h2>', 'chosen by the owner of the organisation.</p><h2>The plan</h2>')), (PAGE, swap(0, '<p class="hint">Built from the reviewed domain <b>Website</b>, ' + CHOSEN + '</p>', ''))]
    unsealed = [
     (WHOLE, Y(0, lambda s: s.update(system_sha256='0' * 64))), (SYSTEM, Y(0, lambda s: s['plan'].update(status='METHOD_ABSENT'))), (PAGE, swap(0, 'Ready: 4 steps', 'Ready: 5 steps')),
     (WHOLE, swap(0, '"PROPOSED_ONLY"', '"APPROVED"', 'system.json')), (WHOLE, lambda d: S(d)[0].update(folder='a-website-for-my-organisation')), (WHOLE, swap(0, '"files"', '"file"', 'manifest.json')),
     (WHOLE, lambda d: S(d)[1].update(folder=S(d)[0]['folder'])), (WHOLE, lambda d: S(d)[0]['files'].update({'index.html': S(d)[0]['files']['index.html'] + '\n'})),
     (WHOLE, lambda d: S(d)[0]['files'].update({'notes.txt': 'mine'})), (WHOLE, lambda d: S(d)[0]['files'].pop('manifest.json')),
     (WHOLE, lambda d: S(d)[0]['files'].update({'index.html': S(d)[0]['files']['index.html'].replace('Proposal only', 'Approved')})),
     (WHOLE, swap(0, 'PROPOSED_ONLY', 'APPROVED', 'workflow.json')), (WHOLE, lambda d: S(d)[0]['files'].update({'index.html': None})),
     (WHOLE, lambda d: S(d)[0].update(folder=S(d)[0]['folder'][:-16] + json.loads(S(d)[0]['files']['system.json'])['system_sha256'][:16])),   # a folder named after the system's digest, not after the bytes of its files
     (SYSTEM, lambda d: d.update(action_handlers=dict(d['action_handlers'], ask=dict(d['action_handlers']['ask'], sha256='0' * 64)))),   # the code the record holds behind a kind is not the code the systems name
     # ---- the command's recorded runs
     (COMMAND, lambda d: d['scenes']['system']['command'][2].update(exit=0)), (COMMAND, lambda d: d['scenes']['system']['command'][3].update(exit=1)), (COMMAND, lambda d: d['scenes']['system']['command'][0].update(exit=False)),
     (COMMAND, lambda d: d['scenes']['system']['command'][3]['stderr'].insert(0, 'usage: g2.py [-h] [--domain DOMAIN] [--out OUT] [--list] [--demo] [words ...]')),
     (COMMAND, lambda d: d['scenes']['system']['command'][2]['stderr'].append('Traceback (most recent call last):')), (COMMAND, lambda d: d['scenes']['system']['command'][0]['written'].pop(S(d)[0]['folder'] + '/manifest.json')),
     (COMMAND, lambda d: d['scenes']['system']['command'][0]['written'].update({S(d)[0]['folder'] + '/index.html': '0' * 64})), (COMMAND, lambda d: d['scenes']['system']['command'][1]['written'].update({'another-folder/index.html': '0' * 64})),
     (COMMAND, lambda d: d['scenes']['system']['command'][2]['written'].pop(S(d)[0]['folder'] + '/notes.txt')), (COMMAND, lambda d: d['scenes']['system']['command'][2]['written'].update({S(d)[0]['folder'] + '/index.html': '0' * 64})),
     (COMMAND, lambda d: d['scenes']['system']['command'][3]['written'].update({'a-site-0000000000000000/index.html': '0' * 64})), (COMMAND, lambda d: d['scenes']['system']['command'][0].update(stdout=['WAITING    a website for my organisation'])),
     (COMMAND, lambda d: d['scenes']['system']['command'][0]['argv'].append('--force')), (COMMAND, lambda d: d['scenes']['system']['command'].pop()), (COMMAND, lambda d: d['scenes']['system']['command'][1].update(stderr=['warning'])),
     (COMMAND, lambda d: d['scenes']['system']['command'][4].update(exit=2)), (COMMAND, lambda d: d['scenes']['system']['command'][4].update(exit=0)),   # a write that could not be reported told as a refusal, or as a success
     (COMMAND, lambda d: d['scenes']['system']['command'][4].update(written={})), (COMMAND, lambda d: d['scenes']['system']['command'][4]['stderr'].append('Traceback (most recent call last):')),
     # ---- case 70
     (CASE70, lambda d: case(d, '70_recorded_open')['outcome'].update(status='PLAN_READY')), (CASE70, lambda d: case(d, '70_recorded_open')['outcome'].update(pending=[])),
     (CASE70, lambda d: case(d, '70_recorded_open')['outcome'].update(actions=[ASK, SHIP])), (CASE70, lambda d: case(d, '70_recorded_open')['outcome'].update(goal_truth_after='TRUE')),
     (CASE70, lambda d: case(d, '70_recorded_open')['outcome']['model_receipts'][0]['ask'].update(to='mallory')), (DOMAIN, lambda d: case(d, '70_recorded_open')['outcome'].update(trace_root_sha256='0' * 64)),
     (CASE70, lambda d: case(d, '70_recorded_open')['derived_state']['facts']['orgA/fulfillment|order_complete'].update(truth='TRUE')),
     (CASE70, lambda d: case(d, '70_recorded_open')['derived_state']['facts']['orgA/fulfillment|order_complete'].update(final=True)),
     (CASE70, lambda d: case(d, '70_recorded_open')['derived_state']['facts']['orgA/fulfillment|order_complete'].update(source='fixture/reviewed')),
     (CASE70, lambda d: case(d, '70_recorded_open')['derived_state']['budget_after'].update(attention=3)), (CASE70, lambda d: case(d, '70_recorded_open')['derived_state']['budget_after'].update(attention=2.0)),
     (CASE70, lambda d: case(d, '70_recorded_open').update(packs=case(d, '70_recorded_open')['packs'][:-1])),
     # what case 70 says beside its runs: the world view of the desk's row, the rule, the scope, the run block, and what its run says beside its trace (in both copies)
     (CASE70, lambda d: case(d, '70_recorded_open')['four_views']['world'][-1].update(truth='TRUE')), (CASE70, lambda d: case(d, '70_recorded_open')['four_views']['world'][-1].update(source='fixture/reviewed')),
     (CASE70, lambda d: case(d, '70_recorded_open')['four_views']['world'].pop()), (CASE70, lambda d: case(d, '70_recorded_open')['four_views']['knowledge'][0]['branches'].reverse()),
     (CASE70, lambda d: case(d, '70_recorded_open')['four_views']['knowledge'][0].update(source='fixture/approved-by-the-board')), (CASE70, lambda d: case(d, '70_recorded_open')['derived_state'].update(rule_ids=[])),
     (CASE70, lambda d: case(d, '70_recorded_open').update(scope='orgB/fulfillment')), (CASE70, lambda d: case(d, '70_recorded_open')['run'].update(status='COMPLETED')),
     (CASE70, lambda d: case(d, '70_recorded_open')['run'].update(goals=[])),
     (CASE70, lambda d: [r.update(needs=[]) for r in (case(d, '70_recorded_open')['outcome'], case(d, '70_recorded_open')['run']['runs'][0])]),
     (CASE70, lambda d: [r.update(proof=['order_complete approved by the board']) for r in (case(d, '70_recorded_open')['outcome'], case(d, '70_recorded_open')['run']['runs'][0])]),
     (CASE70, lambda d: [r.update(selected_branch='R-ORDER@1/OR1') for r in (case(d, '70_recorded_open')['outcome'], case(d, '70_recorded_open')['run']['runs'][0])]),
     (CASE70, lambda d: [r['learning_record'].update(source_trace='0' * 64) for r in (case(d, '70_recorded_open')['outcome'], case(d, '70_recorded_open')['run']['runs'][0])]),
     # ---- case 71
     (CASE71, lambda d: case(d, '71_no_plan_after_a_yes')['outcome'].update(status='PLAN_READY')), (CASE71, lambda d: case(d, '71_no_plan_after_a_yes')['outcome'].update(pending=[RECEIPT])),
     (CASE71, lambda d: case(d, '71_no_plan_after_a_yes')['outcome'].update(goal_truth_before='UNKNOWN')), (CASE71, lambda d: case(d, '71_no_plan_after_a_yes')['outcome']['model_receipts'][0]['ask'].update(to='mallory')),
     (CASE71, lambda d: case(d, '71_no_plan_after_a_yes')['derived_state']['facts']['orgA/closing|order_closed'].update(truth='TRUE')),
     (CASE71, lambda d: case(d, '71_no_plan_after_a_yes')['derived_state']['facts']['orgA/closing|order_closed'].update(source='fixture/reviewed')),
     (CASE71, lambda d: case(d, '71_no_plan_after_a_yes')['derived_state']['budget_after'].update(attention=3)), (DOMAIN, lambda d: case(d, '71_no_plan_after_a_yes')['outcome'].update(trace_root_sha256='0' * 64)),
     (CASE71, lambda d: case(d, '71_no_plan_after_a_yes')['four_views']['world'][0].update(truth='TRUE')), (CASE71, lambda d: case(d, '71_no_plan_after_a_yes')['four_views']['knowledge'][0]['branches'].pop(0)),
     (CASE71, lambda d: [r.update(needs=['refund_recorded']) for r in (case(d, '71_no_plan_after_a_yes')['outcome'], case(d, '71_no_plan_after_a_yes')['run']['runs'][0])]),
     (CASE71, lambda d: [r.update(selected_branch='R-CLOSE@1/OR1') for r in (case(d, '71_no_plan_after_a_yes')['outcome'], case(d, '71_no_plan_after_a_yes')['run']['runs'][0])])]
    missed = [] if len(sealed) + len(unsealed) == FORGED else [f'the number of forgeries ({len(sealed) + len(unsealed)}) is not the number the README quotes ({FORGED})']
    if honest and all(honest.get(name, False) is True for name in NAMES):
        try:
            again = claims(reseal(copy_of()))
        except Exception as e:
            again = {'fault': repr(e)}
        if not all(again.get(name, False) is True for name in NAMES):
            missed.append('an honest copy, resealed, does not pass: ' + str(sorted(k for k, v in again.items() if v is not True or k == 'fault')))
        for label, forgeries, seal in (('sealed', sealed, True), ('unsealed', unsealed, False)):
            for i, (target, change) in enumerate(forgeries):
                why = forged(target, change, seal)
                missed += [f'{label} {i} {why}'] if why else []
    else:
        missed.append('the honest record does not pass')
    return (FORGERIES, not missed, str(missed or fault))


def checks(data, ROOT, sha, check_chain):
    """The nine rows of this version: S120 to S126 and S128 on the record as it stands, S127 on forgeries of it. A record these checks
    cannot read at all is nine failed rows that say so, not an error that ends the verifier."""
    try:
        return rows_of(data, ROOT, sha, check_chain)
    except Exception as e:
        return [(name, False, 'the record cannot be read: ' + type(e).__name__) for name in NAMES + [FORGERIES]]
