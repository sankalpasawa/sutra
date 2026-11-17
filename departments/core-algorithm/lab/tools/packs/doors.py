# 0.21.0-doors: which source may state which fact, and a stop for want of a place, as the program's own records showed them (need N1, N2
# and N3 of the version; ruling R35 of the program: every need was first handed to the parts the lab had; see the recorded sequence `doors`).
# The standing example is a lender. Five desks, each a system that runs on its own and keeps a journal per session. Every pack below is
# made of parts the lab had: goals, rows, rules, methods of the kinds simulate_fact, ask and handoff, grants, providers and a budget. The
# packs are the desks of the program's own examples, in the lab's names: the refund desk and the payout desk of examples 1 and 5, the
# landing of example 2 told as a refund batch, and an agent's desk of the kind the program's runners kept.
LOAN_BOOK = 'system:lendco/loan-book'     # where a desk's facts come from: the lender's loan book, a system the journals let in
FINANCE = 'system:lendco/finance'         # the lender's finance department: the yes of a refund is its fact
OWNER = 'owner:lendco'                    # the lender's owner: the yes of a new way of paying out is the owner's fact
NONE = {'compute': 0, 'money': 0, 'attention': 0}


def cost(**lines):   # a cost on the three budget lines and any line a desk adds
    return dict(NONE, **lines)


def ask(id, effect, requires, to, question, provider):   # a step that puts a question to a party and parks the run: the answer makes the fact
    return method(id, effect, requires, provider=provider, cost=cost(attention=1), action='ask', ask_to=to, question=question)


def handover(id, effect, requires, hand, instruction, checker, line):   # a step whose work is done by a hand outside and checked by a checker's row
    return method(id, effect, requires, provider=hand, cost={line: 1}, action='handoff', handoff_to=hand, instruction=instruction, verified_by=checker)


# The refund desk of example 1: one refund of an overpaid instalment of loan L-17. The loan book says whether the refund is due; the yes is
# finance's, asked by the desk; the refund is the desk's own step and costs one of its three units of money.
pack('315_door_refund_desk', scope='lendco/refund-desk', goals=['refund_sent'],
     budget={'compute': 0, 'money': 3, 'attention': 2}, preference=['money', 'attention', 'compute'],
     methods=[ask('door-ask-finance@1', 'refund_approved_by_finance', ['refund_due'], FINANCE,
                  'Loan L-17 was overpaid on instalment 7. May the desk send the refund?', 'finance-channel'),
              method('door-send-refund@1', 'refund_sent', ['refund_due', 'refund_approved_by_finance'], provider='refund-desk', cost=cost(money=1))],
     providers={'finance-channel': 2, 'refund-desk': 3}, grants=['action:door-ask-finance@1', 'action:door-send-refund@1'])

# The payout desk of example 5: a payout is checked, paid and reconciled, three steps of the desk's own, once for every loan the loan book
# says a payout is due on (each loan is a new version of the row `payout_due`).
pack('316_door_payout_desk', scope='lendco/payouts', goals=['payout_reconciled'],
     budget={'compute': 30, 'money': 6, 'attention': 2}, preference=['money', 'compute', 'attention'],
     methods=[method('door-check-payee@1', 'payee_checked', ['payout_due'], provider='payout-desk', cost=cost(compute=2)),
              method('door-pay@1', 'payout_paid', ['payout_due', 'payee_checked'], provider='payout-desk', cost=cost(compute=1, money=1)),
              method('door-reconcile@1', 'payout_reconciled', ['payout_due', 'payout_paid'], provider='payout-desk', cost=cost(compute=2))],
     providers={'payout-desk': 40}, grants=['action:door-check-payee@1', 'action:door-pay@1', 'action:door-reconcile@1'])
# Example 5 again: a reader of the desk's records says the three steps repeat, and the owner is asked whether a cheaper way may be used.
pack('317_door_change_approval', goals=['payout_reconciled', 'cheaper_way_approved'],
     methods=[ask('door-ask-owner@1', 'cheaper_way_approved', ['payout_chain_repeated'], OWNER,
                  'The last payouts each ran the same three steps. A person wrote one step that does the same for less. May the desk use it from now on?',
                  'owner-channel')],
     providers={'owner-channel': 2}, grants=['action:door-ask-owner@1'])

# The landing of example 2, told as a lender's refund batch: the reconciliation run is handed to a script and checked by the reconciliation
# ledger, then the posting is handed to another script and checked by the posting log. The batch has landed when both facts hold (a rule
# of the owner). Each script has two places, so each piece of work can be handed over twice.
pack('318_door_batch_landing', scope='lendco/refund-batches', goals=['refund_batch_landed'],
     budget={'compute': 0, 'money': 0, 'attention': 0, 'runs': 4}, preference=['runs', 'compute', 'money', 'attention'],
     evidence=[fact('batch_rehearsed', 'TRUE', source=OWNER, version='batch-2026-11')],
     rules=[rule('R-DOOR-BATCH@1', 'refund_batch_landed', [['batch_reconciled', 'batch_posted']],
                 source='the owner: a batch has landed when the reconciliation run passed it and the posting step posted it')],
     methods=[handover('door-run-reconciliation@1', 'batch_reconciled', ['batch_rehearsed'], 'script:reconcile',
                       'Run the reconciliation of refund batch 2026-11 and pass it when every refund matches the loan book.', 'checker:reconciliation-ledger', 'runs'),
              handover('door-post-batch@1', 'batch_posted', ['batch_reconciled'], 'script:post',
                       'Post refund batch 2026-11 to the general ledger and write the posting log.', 'checker:posting-log', 'runs')],
     providers={'script:reconcile': 2, 'script:post': 2}, grants=['action:door-run-reconciliation@1', 'action:door-post-batch@1'])

# An agent's desk of the kind the program's runners kept: the review of one loan file is five pieces of work in a row, each handed to one
# reviewer and checked by the review notes. The desk's own pack gives the reviewer one place.
pack('319_door_file_review', scope='lendco/file-review', goals=['loan_file_reviewed'],
     budget={'compute': 10, 'money': 10, 'attention': 3, 'agent_runs': 8}, preference=['agent_runs', 'compute', 'money', 'attention'],
     evidence=[fact('review_handed_over', 'TRUE', source='journal:servicing-desk', version='loan L-52, try 1')],
     methods=[handover('door-read-loan-file@1', 'loan_file_read', ['review_handed_over'], 'agent:file-reviewer',
                       'Read the file of loan L-52 and write down what it says.', 'checker:review-notes', 'agent_runs'),
              handover('door-check-instalments@1', 'instalments_checked', ['loan_file_read'], 'agent:file-reviewer',
                       'Check every instalment of loan L-52 against the loan book.', 'checker:review-notes', 'agent_runs'),
              handover('door-check-arrears@1', 'arrears_checked', ['instalments_checked'], 'agent:file-reviewer',
                       'Check whether loan L-52 is in arrears and since when.', 'checker:review-notes', 'agent_runs'),
              handover('door-write-findings@1', 'findings_written', ['arrears_checked'], 'agent:file-reviewer',
                       'Write the findings of the review of loan L-52.', 'checker:review-notes', 'agent_runs'),
              handover('door-close-review@1', 'loan_file_reviewed', ['findings_written'], 'agent:file-reviewer',
                       'Close the review of loan L-52 and file it.', 'checker:review-notes', 'agent_runs')],
     providers={'agent:file-reviewer': 1},
     grants=['action:door-read-loan-file@1', 'action:door-check-instalments@1', 'action:door-check-arrears@1', 'action:door-write-findings@1',
             'action:door-close-review@1'])
