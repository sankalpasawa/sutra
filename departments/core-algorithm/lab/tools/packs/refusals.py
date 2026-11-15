# 0.15.0-refusals: what a department refuses and what it always asks (matrix rows R49, R103, R37). The standing example is a lender.
import json
from extensions.refusals_classes import CLASSES, screened, prerequisites, unscreened, unruled
from extensions.refusals_narrowing import relaxations, verdict, install_rule

made = {}
def keep(name, **fields):   # author a pack, and keep what its file holds for the authoring-time checks below
    pack(name, **fields)
    made[name] = json.loads(json.dumps({'schema': 'sutra-extension/2', 'id': name, **fields}))
def decision(predicate, truth, source, version, **more):   # a decision: a final row that rests on nothing else
    return {'predicate': predicate, 'truth': truth, 'verified': True, 'final': True, 'source': source, 'version': version, **more}

# R49. An operations desk rules on every class of the classifier's table, once per class and not per request: never is a
# decision (a final FALSE row) on may:<class>, always an ordinary TRUE row. Ten classes, ten rulings: no step can meet a class
# nobody ruled on (the audit below), so a refused class names its look REFUSED whatever else the step is in.
RULINGS = {'history_rewrite': ('never', 'Never rewrite or discard shared git history.'),
           'recursive_delete': ('never', 'Never delete a tree outside the build folders.'),
           'disk_or_system': ('never', 'Never touch disks, mounts or system services.'),
           'remote_mutation': ('always', 'Copies and syncs to the branch servers may run.'),
           'privilege_escalation': ('never', 'Never run anything as another user.'),
           'unreadable_command': ('never', 'Never run a command that cannot be read by its words.'),
           'destructive_tool': ('never', 'Never call a tool that deletes, drops or purges.'),
           'bulk_tool': ('always', 'The monthly bulk update of the dunning list may run.'),
           'credential_path': ('never', 'Never touch a credential store.'),
           'private_host': ('never', 'Never fetch anything but a plain public web address.')}
assert list(RULINGS) == list(CLASSES)   # the desk's lines follow the table, class by class
keep('110_ops_desk', scope='lendco/operations', budget={'compute': 10, 'money': 10, 'attention': 3}, preference=['compute', 'money', 'attention'],
     providers={'local-provider': 8},
     evidence=[decision('may:' + c, 'FALSE', 'owner:lendco/operations', 'denylist-1', tag=tag, line=line) if tag == 'never' else
               dict(fact('may:' + c, 'TRUE', source='owner:lendco/operations', version='denylist-1'), tag=tag, line=line) for c, (tag, line) in RULINGS.items()])
assert unruled(made['110_ops_desk']) == []   # the authoring-time audit of the desk: it rules on every class of the table
# The desk's queue: eight requested actions (commands, a tool, a path, a host). Each step is authored through the classifier:
# its screening row, named by the digest of its request, and as prerequisites that row and the permission of every class the
# request is in. Every grant is held.
QUEUE = [('restart-ledger-sync@1', 'ledger_sync_restarted', {'kind': 'command', 'text': 'sudo systemctl restart ledger-sync'}),
         ('mail-due-list@1', 'due_list_mailed', {'kind': 'command', 'text': 'python3 reports/due_list.py --month 2026-11 | mail -s due ops@lendco.example'}),
         ('purge-dunning-queue@1', 'dunning_queue_purged', {'kind': 'tool', 'text': 'collections__purge_dunning_queue'}),
         ('read-bank-keys@1', 'bank_keys_read', {'kind': 'path', 'text': '~/.aws/credentials'}),
         ('fetch-instance-metadata@1', 'instance_metadata_fetched', {'kind': 'host', 'text': 'http://169.254.169.254/latest/meta-data/'}),
         ('export-due-list@1', 'due_list_exported', {'kind': 'command', 'text': 'python3 reports/due_list.py --month 2026-11'}),
         ('sync-loan-book-as-root@1', 'loan_book_synced_as_root', {'kind': 'command', 'text': 'sudo rsync -a loans/ backup:/srv/loans/'}),
         ('push-rate-table@1', 'rate_table_pushed', {'kind': 'command', 'text': 'rsync -a rates/ branch-01:/srv/rates/'})]
keep('111_requested_actions', scope='lendco/operations', goals=[effect for _, effect, _ in QUEUE],
     evidence=[screened(step, request) for step, _, request in QUEUE],
     methods=[method(step, effect, prerequisites(step, request), request=request) for step, effect, request in QUEUE],
     grants=['action:' + step for step, _, _ in QUEUE])
assert unscreened(made['111_requested_actions'], every=True) == []   # the authoring-time audit of the queue: every step was screened and requires what its request needs
# Counterexample: a team's later pack on the desk (the platform team) that brings a method of its own for a refused permission,
# its grant and a bigger budget. The kernel applies it and refuses as before; the narrowing check names the looser line and the
# raised ceilings.
keep('119_platform_allows_itself', scope='lendco/operations', methods=[method('permit-root@1', 'may:privilege_escalation', [], cost={'compute': 0, 'money': 0, 'attention': 0})],
     grants=['action:permit-root@1'], budget={'compute': 50, 'money': 50})
assert [(f['kind'], f['how']) for f in relaxations([made['110_ops_desk'], made['111_requested_actions']], made['119_platform_allows_itself'])] == [
    ('REFUSAL_DROPPED', 'looser'), ('CEILING_RAISED', 'budget'), ('CEILING_RAISED', 'budget')]

# R103. A team's standing rules as packs. The team's defaults first: a refund of an overpaid instalment is paid and reconciled.
# Its steps are written around three facts the team does not decide itself (the payee check, the owner's approval, the
# third-party route): alone, the team does not know whether it may pay.
keep('112_servicing_team', scope='lendco/servicing', goals=['refund_settled'], budget={'compute': 10, 'money': 10, 'attention': 3},
     preference=['compute', 'money', 'attention'],
     rules=[rule('R-REFUND@1', 'refund_settled', [['refund_paid', 'payment_reconciled']], source='reviewed/servicing-team')],
     evidence=[fact('refund_due', 'TRUE', source='fixture/loan-book', version='overpaid-instalment-1'),
               fact('maker_may_reconcile', 'TRUE', source='fixture/team-default', version='1')],
     methods=[method('check-payee-account@1', 'payee_account_checked', ['refund_due'], cost={'compute': 1, 'money': 0, 'attention': 0}),
              method('pay-to-borrower@1', 'refund_paid', ['payee_account_checked', 'owner_approved_refund'], cost={'compute': 1, 'money': 2, 'attention': 0}),
              method('pay-to-third-party@1', 'refund_paid', ['third_party_payout_allowed'], cost={'compute': 1, 'money': 1, 'attention': 0}),
              method('reconcile-by-maker@1', 'payment_reconciled', ['maker_may_reconcile', 'refund_paid'], cost={'compute': 1, 'money': 0, 'attention': 0}),
              method('reconcile-by-checker@1', 'payment_reconciled', ['refund_paid'], cost={'compute': 2, 'money': 0, 'attention': 0})],
     providers={'local-provider': 6},
     grants=['action:pay-to-borrower@1', 'action:pay-to-third-party@1', 'action:reconcile-by-maker@1', 'action:reconcile-by-checker@1'])
# The owner's three lines, each as the pack construct that enforces it: always = a grant that is held, ask = a step of kind ask
# before the work, never = a decision no rule or method overturns. (J2 Pro hands such lines to the team as guidance: practice.py.)
keep('113_servicing_standing_rules', scope='lendco/servicing',
     standing_rules=[{'tag': 'always', 'line': "Always check the payee's account against the loan book before a refund is paid.", 'grant': 'action:check-payee-account@1'},
                     {'tag': 'ask', 'line': 'Ask me first before a refund is paid.', 'method': 'ask-owner-refund@1'},
                     {'tag': 'never', 'line': "Never pay a refund to an account that is not the borrower's own.", 'decision': 'third_party_payout_allowed'}],
     grants=['action:check-payee-account@1', 'action:ask-owner-refund@1'],
     methods=[method('ask-owner-refund@1', 'owner_approved_refund', [], provider='owner-channel', cost={'compute': 0, 'money': 0, 'attention': 1}, action='ask',
                     question='A refund of an overpaid instalment is due to the borrower. May it be paid?', ask_to='owner')],
     providers={'owner-channel': 1},
     evidence=[decision('third_party_payout_allowed', 'FALSE', 'owner:lendco/servicing', 'standing-rules-1', tag='never')])
# A practice pick on top (J2 Pro's "Money movement", two of its lines word for word): it only adds. The always line is a duty,
# so it is a condition added to the rule and a step whose grant is held; the never line closes the cheaper reconciliation.
keep('114_practice_money_movement', scope='lendco/servicing',
     practice={'id': 'money-movement', 'name': 'Money movement', 'from': 'sutra-pro/sutra_app/library/specs/practice_packs.json'},
     standing_rules=[{'function': 'identity', 'tag': 'always', 'line': 'Every money effect names its source record (the bank file, a ledger row or a payment reference) before it is judged.',
                      'rule': 'R-REFUND@2', 'grant': 'action:name-source-record@1'},
                     {'function': 'coordination', 'tag': 'never', 'line': 'A payment and its reconciliation are never held by the same person or model: one makes, another checks.',
                      'decision': 'maker_may_reconcile'}],
     rules=[rule('R-REFUND@2', 'refund_settled', [['source_record_named', 'refund_paid', 'payment_reconciled']], replaces='R-REFUND@1', source='practice/money-movement')],
     methods=[method('name-source-record@1', 'source_record_named', ['refund_due'], cost={'compute': 1, 'money': 0, 'attention': 0})],
     grants=['action:name-source-record@1'],
     evidence=[decision('maker_may_reconcile', 'FALSE', 'practice:money-movement', 'practice-1', tag='never')])
# R37. Counterexample: a later pack of the team that says three things more loosely. The kernel applies it; the check names it.
keep('115_servicing_loosens', scope='lendco/servicing',
     rules=[rule('R-REFUND@3', 'refund_settled', [['refund_paid', 'payment_reconciled']], replaces='R-REFUND@2', source='draft/servicing-team')],
     evidence=[decision('third_party_payout_allowed', 'TRUE', 'team:lendco/servicing', 'draft-1'),
               fact('owner_approved_refund', 'TRUE', source='team:lendco/servicing', version='draft-1')])
TEAM = [made['112_servicing_team'], made['113_servicing_standing_rules']]
PRACTICE = TEAM + [made['114_practice_money_movement']]
assert relaxations(TEAM, made['114_practice_money_movement']) == []   # checked when authored: the practice pick only adds
assert [f['kind'] for f in relaxations(PRACTICE, made['115_servicing_loosens'])] == ['CONDITION_DROPPED', 'REFUSAL_DROPPED', 'ASK_DROPPED']
# The verdict as evidence (the pattern of the workflow standard, packs 60 to 64): may this child pack be installed over those?
# The review desk holds one install rule per comparison; each rests on the verdict of exactly that comparison (the child and the
# digest of the packs compared), so the review of another child, or of another text of the same child, cannot stand in.
RULES = [install_rule(PRACTICE, made['115_servicing_loosens']), install_rule(TEAM, made['114_practice_money_movement'])]
keep('116_pack_review', scope='lendco/pack-review', goals=[r['head'] for r in RULES], rules=RULES)
keep('117_review_of_loosening', scope='lendco/pack-review', evidence=[verdict(PRACTICE, made['115_servicing_loosens'])])
keep('118_review_of_practice', scope='lendco/pack-review', evidence=[verdict(TEAM, made['114_practice_money_movement'])])
