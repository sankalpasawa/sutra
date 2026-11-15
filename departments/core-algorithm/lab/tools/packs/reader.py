# 0.19.0-reader: learning from past runs (ruling R27 of the program, tried under R35: a need is first met from the algorithm as it stands).
# The standing example is a lender. Three desks, each a system that runs on its own and keeps a journal; the reader (extensions/reader.py) reads
# that journal and says what repeated. Everything below is made of parts the lab had: goals, rows, a rule, methods, grants. No new action kind.
#
# A change to a desk's own ways is a piece of work like any other. The desk's changes pack says how a change is approved here: the fact
# `<thing>_repeated` is the row the reader words from the record (it enters at the journal's event door), and the yes is a step that requires it.
# How weighty a change is, is ONE value row with its answers resting on it (an axis written by hand): the desk's own yes requires the answer
# `change_weight=small`, the independent checker's yes requires `change_weight=weighty`. An answer row rests on the value row at the version that
# is the value, so it reads only while the value row carries the value it was written for: the two approvers read one answer.
BOOK = 'fixture/loan-book'          # where a desk's facts come from: the loan book
POLICY = 'fixture/change-policy'    # who says how weighty a change is
FREE = {'compute': 0, 'money': 0, 'attention': 0}


def cost(**lines):   # a cost on the three budget lines; a token is one unit of `compute`
    return dict(FREE, **lines)


def weight(value):   # the axis: the value row, then one row per answer, each resting on the value row at the version that is the value
    rests = [{'predicate': 'change_weight', 'version': value}]
    return [fact('change_weight', 'TRUE', source=POLICY, version=value)] + [
        dict(fact('change_weight=' + answer, 'TRUE' if answer == value else 'FALSE', source=POLICY, version=value), depends_on=rests) for answer in ('small', 'weighty')]


# The collections desk reminds a borrower whose instalment is overdue. Its reminder step requires the fact `borrower_reachable`, which holds
# only through the desk's rule (a phone number or an address is on file): no stored row says it. The kernel offers the plan, and at the step's
# turn the fact is no stored row that reads TRUE, so the step stops. It stops the same way at every look: a stop does not feed the next plan.
pack('220_collections_desk', scope='lendco/collections', goals=['reminder_sent'],
     budget={'compute': 12, 'money': 0, 'attention': 0}, preference=['compute', 'money', 'attention'],
     evidence=[fact('instalment_overdue', 'TRUE', source=BOOK, version='loan-7-day-1'), fact('phone_on_file', 'TRUE', source=BOOK, version='loan-7')],
     rules=[rule('R-REACHABLE@1', 'borrower_reachable', [['phone_on_file'], ['address_on_file']])],
     methods=[method('send-reminder@1', 'reminder_sent', ['instalment_overdue', 'borrower_reachable'], cost=cost(compute=1))],
     providers={'local-provider': 6}, grants=['action:send-reminder@1'])
# How this desk takes a change to its own ways. The lesson about the reminder is a small change: the desk's own yes, one token.
pack('221_collections_changes', goals=['reminder_sent', 'reminder_lesson_approved'], evidence=weight('small'),
     methods=[method('approve-own-reminder-lesson@1', 'reminder_lesson_approved', ['reminder_stop_repeated', 'change_weight=small'], cost=cost(compute=1)),
              method('check-reminder-lesson-independently@1', 'reminder_lesson_approved', ['reminder_stop_repeated', 'change_weight=weighty'],
                     provider='independent-checker', cost=cost(compute=5))],
     providers={'independent-checker': 1}, grants=['action:approve-own-reminder-lesson@1', 'action:check-reminder-lesson-independently@1'])
# The lesson itself, written by a person: a way that requires the stored fact, and the grant of the way that stops is taken away.
# It also ends the change as a standing goal of the desk: the change is a piece of work, and with this pack it is finished.
pack('222_reminder_lesson', goals=['reminder_sent'],
     methods=[method('send-reminder-by-phone@1', 'reminder_sent', ['instalment_overdue', 'phone_on_file'], cost=cost(compute=1))],
     grants=['action:send-reminder-by-phone@1'], revoke_grants=['action:send-reminder@1'])
# The same lesson judged weighty: the value and its answers restated in one pack, which applies whole or not at all.
pack('223_lesson_judged_weighty', evidence=weight('weighty'))

# The payout desk pays out a loan in three steps: check the payee, pay, reconcile. Every step names the payout it works on (`payout_due`)
# among its prerequisites, so a new payout makes every row of the last one read UNKNOWN and every step runs and is paid again.
pack('224_payout_desk', scope='lendco/payouts', goals=['payout_reconciled'],
     budget={'compute': 30, 'money': 6, 'attention': 0}, preference=['compute', 'money', 'attention'],
     evidence=[fact('payout_due', 'TRUE', source=BOOK, version='loan-101')],
     methods=[method('check-payout-payee@1', 'payee_checked', ['payout_due'], cost=cost(compute=2)),
              method('pay-payout@1', 'payout_paid', ['payout_due', 'payee_checked'], cost=cost(compute=1, money=1)),
              method('reconcile-payout@1', 'payout_reconciled', ['payout_due', 'payout_paid'], cost=cost(compute=2))],
     providers={'local-provider': 12}, grants=['action:check-payout-payee@1', 'action:pay-payout@1', 'action:reconcile-payout@1'])
# A new way to pay out is a weighty change: the yes of an independent checker, five tokens, another holder.
pack('225_payout_changes', goals=['payout_reconciled', 'payout_way_approved'], evidence=weight('weighty'),
     methods=[method('approve-own-payout-way@1', 'payout_way_approved', ['payout_chain_repeated', 'change_weight=small'], cost=cost(compute=1)),
              method('check-payout-way-independently@1', 'payout_way_approved', ['payout_chain_repeated', 'change_weight=weighty'],
                     provider='independent-checker', cost=cost(compute=5))],
     providers={'independent-checker': 1}, grants=['action:approve-own-payout-way@1', 'action:check-payout-way-independently@1'])
# The chain as one step, written by a person: the same fact made, the same fact required, two tokens where the chain costs five.
pack('226_payout_in_one', goals=['payout_reconciled'],
     methods=[method('settle-payout-in-one@1', 'payout_reconciled', ['payout_due'], cost=cost(compute=2, money=1))],
     grants=['action:settle-payout-in-one@1'])
# The independent checker is away: its slots are restated to none, so no step can give the yes to a weighty change.
pack('227_checker_away', providers={'independent-checker': 0})

# The waiver desk waives the late fee of a loan when finance says it may. The lab has no parameters, so every loan is a fact of its own and has
# its own two steps: one asks finance (the same words each time, put to the same party), one waives. The yes to a change of this desk is asked
# of another system, finance itself: the question goes out once the reader's row is in, and at the answer door only finance's answer is taken.
FINANCE = 'system:lendco/finance'
MAY_WAIVE = 'May the late fee of this loan be waived?'


def loan(n):   # one loan's request, its question to finance and its waiver
    return (fact(f'waiver_requested_{n}', 'TRUE', source=BOOK, version=f'loan-{n}'),
            method(f'ask-finance-waiver-{n}@1', f'waiver_approved_{n}', [], provider='finance-channel', cost=cost(attention=1), action='ask', question=MAY_WAIVE, ask_to=FINANCE),
            method(f'waive-late-fee-{n}@1', f'fee_waived_{n}', [f'waiver_requested_{n}', f'waiver_approved_{n}'], cost=cost(compute=1)))


LOANS = [loan(n) for n in (201, 202, 203)]
pack('228_waiver_desk', scope='lendco/waivers', goals=['fee_waived_201', 'fee_waived_202', 'fee_waived_203', 'own_waivers_approved'],
     budget={'compute': 8, 'money': 0, 'attention': 4}, preference=['compute', 'money', 'attention'],
     evidence=[row for row, _, _ in LOANS],
     methods=[m for _, ask, waive in LOANS for m in (ask, waive)] + [
         method('ask-finance-own-waivers@1', 'own_waivers_approved', ['waiver_answer_repeated'], provider='finance-channel', cost=cost(attention=1), action='ask',
                question='Finance gave the same answer each time the waiver desk asked. May the desk decide waivers of this kind on its own from now on?', ask_to=FINANCE)],
     providers={'local-provider': 6, 'finance-channel': 4},
     grants=[m['grant'] for _, ask, waive in LOANS for m in (ask, waive)] + ['action:ask-finance-own-waivers@1'])
# The rule that came of the repeated answer, written by a person: for the next loan the desk's own yes stands where the question to finance stood.
pack('229_own_waivers', goals=['fee_waived_204'],
     evidence=[fact('waiver_requested_204', 'TRUE', source=BOOK, version='loan-204')],
     methods=[method('approve-own-waiver-204@1', 'waiver_approved_204', ['waiver_requested_204'], cost=cost(compute=1)),
              method('waive-late-fee-204@1', 'fee_waived_204', ['waiver_requested_204', 'waiver_approved_204'], cost=cost(compute=1))],
     grants=['action:approve-own-waiver-204@1', 'action:waive-late-fee-204@1'])
