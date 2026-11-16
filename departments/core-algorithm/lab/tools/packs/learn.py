# 0.20.0-learn: the learn feature reads every check with the checker's own words, several records at once, and who stated a fact against
# what the plan says (ruling R35 of the program: the need was first handed to the parts the lab had; see the recorded sequences).
# The standing example is a lender. Three desks, each a system that runs on its own. A desk keeps one journal per session (a record); the
# learn feature (extensions/learn.py) reads the records. Everything below is made of parts the lab had: goals, rows, methods of the kinds
# simulate_fact, ask and handoff, grants and providers. No new action kind, no new key.
BOOK = 'fixture/loan-book'                # where a desk's facts come from: the loan book
FINANCE = 'system:lendco/finance'         # another system: the lender's finance department
FREE = {'compute': 0, 'money': 0, 'attention': 0}


def cost(**lines):   # a cost on the three budget lines
    return dict(FREE, **lines)


def handover(id, effect, requires, hand, instruction, checker):   # a step whose work is done by a hand outside and checked by a checker's row
    return method(id, effect, requires, provider=hand, cost=cost(compute=1), action='handoff', handoff_to=hand, instruction=instruction, verified_by=checker)


# The servicing desk sends a borrower the annual statement of a loan. Writing it is real work: it is handed over to a writer and checked by the
# statement review against the loan book. The writer's provider has three places, so the work can be handed over three times.
pack('310_learn_statements', scope='lendco/servicing', goals=['statement_sent'],
     budget={'compute': 8, 'money': 0, 'attention': 0}, preference=['compute', 'money', 'attention'],
     evidence=[fact('statement_due', 'TRUE', source=BOOK, version='loan-31-year-2026')],
     methods=[handover('learn-send-statement@1', 'statement_sent', ['statement_due'], 'agent:statement-writer',
                       'Write and send the annual statement of loan L-31.', 'checker:statement-review')],
     providers={'agent:statement-writer': 3}, grants=['action:learn-send-statement@1'])
# The program above the desk judges the month: the servicing lead gives an account of it, and a judge of the program checks that account.
pack('311_learn_month_judged', goals=['statement_sent', 'servicing_month_judged'],
     methods=[handover('learn-judge-servicing-month@1', 'servicing_month_judged', ['statement_sent'], 'agent:servicing-lead',
                       "Give the program an account of this month's statements.", 'checker:program-judge')],
     providers={'agent:servicing-lead': 1}, grants=['action:learn-judge-servicing-month@1'])

# The collections desk calls a borrower whose instalment is in arrears. The call is real work, handed to a collector and checked against the
# call log. The desk's own pack names the collector and gives it no place; every morning the desk starts a new session (a journal of its own),
# and until the day's roster (pack 313) gives the collector two places, a look is blocked for want of a place.
pack('312_learn_collections', scope='lendco/collections-calls', goals=['arrears_call_made'],
     budget={'compute': 6, 'money': 0, 'attention': 0}, preference=['compute', 'money', 'attention'],
     evidence=[fact('arrears_due', 'TRUE', source=BOOK, version='loan-44')],
     methods=[handover('learn-call-borrower@1', 'arrears_call_made', ['arrears_due'], 'agent:collector',
                       'Call the borrower of loan L-44 about the instalment in arrears.', 'checker:call-log')],
     providers={'agent:collector': 0}, grants=['action:learn-call-borrower@1'])
pack('313_learn_roster', providers={'agent:collector': 2})

# The refund desk sends a refund of an overpaid instalment. The plan gives each fact to someone: the yes to finance (a question put to another
# system), the check of the amount to reconciliation (a hand-over to a reconciler, checked by the reconciliation checker), the refund itself to
# the desk's own step. Other sources can still hand in a row on those facts at the event door: the loan book, an auditor.
pack('314_learn_refunds', scope='lendco/refunds', goals=['refund_sent'],
     budget={'compute': 6, 'money': 2, 'attention': 2}, preference=['compute', 'money', 'attention'],
     evidence=[fact('refund_due', 'TRUE', source=BOOK, version='loan-17-instalment-7')],
     methods=[method('learn-ask-finance-refund@1', 'refund_approved', ['refund_due'], provider='finance-channel', cost=cost(attention=1), action='ask',
                     question='Loan L-17 was overpaid on instalment 7. May the desk send the refund?', ask_to=FINANCE),
              handover('learn-reconcile-refund@1', 'refund_reconciled', ['refund_due'], 'agent:reconciler',
                       'Check the refund of loan L-17 against the loan book.', 'checker:reconciliation'),
              method('learn-send-refund@1', 'refund_sent', ['refund_due', 'refund_approved', 'refund_reconciled'], cost=cost(compute=1, money=1))],
     providers={'local-provider': 2, 'finance-channel': 2, 'agent:reconciler': 2},
     grants=['action:learn-ask-finance-refund@1', 'action:learn-reconcile-refund@1', 'action:learn-send-refund@1'])
