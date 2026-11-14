# 0.17.0-queue: three matrix rows about choosing and telling, on one lending company (lendco). Packs 130 to 139.
# This file imports nothing of the lab: tools/make_packs.py runs it on its own.

# ---- R31b, rank a queue by impact. Collections: four borrowers are overdue and the desk has attention for two calls today.
# The queue arrives in loan-number order. Each goal's rule declares its impact (the amount at risk, in thousands): pack content the kernel keeps and never reads.
# Loan 1041 has a second route: a letter costs money and none of the desk's attention.
_QUEUE=dict(scope='lendco/collections',
     goals=['loan_1041_promise','loan_1042_promise','loan_1043_promise','loan_1044_promise'],
     budget={'compute':10,'money':10,'attention':2},preference=['money','attention','compute'],
     rules=[rule('R-PROMISE-1041@1','loan_1041_promise',[['borrower_1041_called'],['borrower_1041_written']],source='reviewed/collections-charter',impact=2),
            rule('R-PROMISE-1042@1','loan_1042_promise',[['borrower_1042_called']],source='reviewed/collections-charter',impact=9),
            rule('R-PROMISE-1043@1','loan_1043_promise',[['borrower_1043_called']],source='reviewed/collections-charter',impact=5),
            rule('R-PROMISE-1044@1','loan_1044_promise',[['borrower_1044_called']],source='reviewed/collections-charter',impact=5)],
     evidence=[fact(f'loan_{n}_overdue','TRUE',source='fixture/due-list') for n in (1041,1042,1043,1044)],
     methods=[method('call-1041@1','borrower_1041_called',['loan_1041_overdue'],provider='collections-desk',cost={'compute':1,'money':0,'attention':1}),
              method('write-1041@1','borrower_1041_written',['loan_1041_overdue'],provider='collections-desk',cost={'compute':1,'money':1,'attention':0}),
              method('call-1042@1','borrower_1042_called',['loan_1042_overdue'],provider='collections-desk',cost={'compute':1,'money':0,'attention':1}),
              method('call-1043@1','borrower_1043_called',['loan_1043_overdue'],provider='collections-desk',cost={'compute':1,'money':0,'attention':1}),
              method('call-1044@1','borrower_1044_called',['loan_1044_overdue'],provider='collections-desk',cost={'compute':1,'money':0,'attention':1})],
     providers={'collections-desk':5},
     grants=['action:call-1041@1','action:write-1041@1','action:call-1042@1','action:call-1043@1','action:call-1044@1'])
pack('130_collections_queue',**_QUEUE)
# The ranking is a pack too: the goals, highest impact first (equal impacts in queue order), and under ranked_by the impact and the rule that put each goal where it is.
# It is worked out here from the rules above. extensions/queue_rank.py makes this very pack from the State pack 130 builds: tests/test_queue.py and check S80 hold the two together.
_RULE={r['head']:r for r in _QUEUE['rules']}
_LINES=sorted(({'goal':g,'impact':_RULE[g]['impact'],'rule':_RULE[g]['id']} for g in _QUEUE['goals']),key=lambda line:-line['impact'])
pack('131_queue_ranked',goals=[line['goal'] for line in _LINES],ranked_by=_LINES)

# ---- R91, the decision-provenance row. A loan desk's day: six standing goals meet the gate in six different ways.
# 7001 is granted and runs; 7002 lacks its grant; 7003 asks the credit head (the desk has attention for exactly that one question); 7004 has no free provider;
# 7005 costs more money than 7001 left; 7006 has no meaning yet.
# The desk's first rule writes a word where an impact belongs: tools/scenes/queue_rank.py records that a queue holding such a goal is not ranked.
pack('132_loan_desk',scope='lendco/loan-desk',
     goals=['loan_7001_disbursed','fee_7002_waived','limit_7003_raised','statement_7004_posted','audit_7005_sampled','writeoff_7006_booked'],
     budget={'compute':10,'money':10,'attention':1},preference=['compute','money','attention'],
     rules=[rule('R-DISBURSE-7001@1','loan_7001_disbursed',[['kyc_7001_verified','funds_7001_released']],source='reviewed/loan-desk-charter',impact='high'),
            rule('R-LIMIT-7003@1','limit_7003_raised',[['head_7003_approved','limit_7003_updated']],source='reviewed/loan-desk-charter')],
     evidence=[fact('application_7001_complete','TRUE',source='fixture/loan-file')],
     methods=[method('verify-kyc-7001@1','kyc_7001_verified',['application_7001_complete'],provider='ops-desk',cost={'compute':1}),   # names one line of the budget: it costs nothing on the others
              method('release-funds-7001@1','funds_7001_released',['kyc_7001_verified'],provider='ops-desk',cost={'compute':1,'money':2,'attention':0}),
              method('waive-fee-7002@1','fee_7002_waived',[],provider='ops-desk',cost={'compute':1,'money':1,'attention':0}),
              method('ask-credit-head-7003@1','head_7003_approved',[],provider='credit-head',cost={'compute':0,'money':0,'attention':1},action='ask',
                     question='May the limit on loan 7003 be raised?',ask_to='credit-head'),
              method('update-limit-7003@1','limit_7003_updated',['head_7003_approved'],provider='ops-desk',cost={'compute':1,'money':0,'attention':0}),
              method('post-statement-7004@1','statement_7004_posted',[],provider='print-room',cost={'compute':1,'money':1,'attention':0}),
              method('sample-audit-7005@1','audit_7005_sampled',[],provider='ops-desk',cost={'compute':1,'money':9,'attention':0})],
     providers={'ops-desk':6,'credit-head':1,'print-room':0},
     grants=['action:verify-kyc-7001@1','action:release-funds-7001@1','action:ask-credit-head-7003@1','action:update-limit-7003@1',
             'action:post-statement-7004@1','action:sample-audit-7005@1'])

# ---- R101, problem styles. Credit-Ops declares its styles in one reviewed rule on the goal: one branch per style (the router's row, then the card's head)
# and one last branch for a problem that fits none of them (the router's row `styled_unmatched`, then the charter owner's answer to one question).
# A style is a card: a pack with its own rule for done-when, its own methods and its own grants. Which style a problem has is a row the router writes
# (matching words to a style is outside); the router matches against the declared styles, so it names one of them or says the problem is unmatched.
_FALLBACK='ask the charter owner: a new home, or a new style'
def _card(style,what_is_missing,cause_effect,reach,cadence,vehicle,verify,gate):   # four descriptors and four handling defaults: pack content the kernel keeps and never reads
    return {'style':style,'what_is_missing':what_is_missing,'cause_effect':cause_effect,'reach':reach,'cadence':cadence,
            'vehicle':vehicle,'verify':verify,'gate':gate,'unmatched':_FALLBACK}
def _routed(style,version='r1'):   # the router's row: one verified TRUE row per problem
    return [fact('styled_'+style,'TRUE',source='router/credit-ops',version=version)]
_STYLES=[['styled_by_the_book','resolved_by_the_book'],['styled_incident','resolved_as_incident']]
_UNMATCHED=['styled_unmatched','new_home_8801_agreed']
# The desk: the goal, the declaration, and the fallback the declaration names. The complaint is closed for this desk when a declared style's card resolved it,
# or when it fits no style and the charter owner agreed to give it a new home. The owner's no means: it stays, and a new style is to be declared here.
pack('133_complaint_desk',scope='lendco/credit-ops',goals=['complaint_8801_closed'],
     budget={'compute':10,'money':10,'attention':2},preference=['compute','money','attention'],learning=True,
     rules=[rule('R-STYLES@1','complaint_8801_closed',_STYLES+[_UNMATCHED],source='reviewed/credit-ops-charter',styles=['run-the-book','incident'],unmatched=_FALLBACK)],
     evidence=[fact('complaint_8801_logged','TRUE',source='fixture/complaints-inbox')],
     methods=[method('ask-new-home-8801@1','new_home_8801_agreed',['complaint_8801_logged'],provider='charter-owner',cost={'compute':0,'money':0,'attention':1},action='ask',
                     question='Complaint 8801 fits no declared style of Credit-Ops. Does it go to a new home? (No: it stays, and a new style is to be declared here.)',
                     ask_to='charter-owner')],
     providers={'charter-owner':1},grants=['action:ask-new-home-8801@1'])
pack('134_style_run_the_book',
     rules=[rule('R-STYLE-RUN-THE-BOOK@1','resolved_by_the_book',[['ledger_8801_matched','reversal_8801_posted']],source='reviewed/style-card',
                 card=_card('run-the-book','T1 known-known','predictable','in-system','event-driven','local workflow','the ledger matches and the reversal is posted','auto'))],
     methods=[method('match-ledger-8801@1','ledger_8801_matched',['complaint_8801_logged'],provider='ops-desk',cost={'compute':1,'money':0,'attention':0}),
              method('post-reversal-8801@1','reversal_8801_posted',['ledger_8801_matched'],provider='ops-desk',cost={'compute':1,'money':1,'attention':0})],
     providers={'ops-desk':4},grants=['action:match-ledger-8801@1','action:post-reversal-8801@1'])
pack('135_style_incident',
     rules=[rule('R-STYLE-INCIDENT@1','resolved_as_incident',[['cause_8801_written','fix_8801_signed_off','customer_8801_told']],source='reviewed/style-card',
                 card=_card('incident','T3 unknown-known','judgment-heavy','in-system','one-off','local workflow','the cause is written, the head of operations signed the fix, the customer was told','ask'))],
     methods=[method('write-cause-8801@1','cause_8801_written',['complaint_8801_logged'],provider='ops-desk',cost={'compute':2,'money':0,'attention':0}),
              method('ask-signoff-8801@1','fix_8801_signed_off',['cause_8801_written'],provider='ops-head',cost={'compute':0,'money':0,'attention':1},action='ask',
                     question='Is the fix for complaint 8801 good to close?',ask_to='ops-head'),
              method('tell-customer-8801@1','customer_8801_told',['fix_8801_signed_off'],provider='ops-desk',cost={'compute':1,'money':0,'attention':0})],
     providers={'ops-desk':4,'ops-head':1},grants=['action:write-cause-8801@1','action:ask-signoff-8801@1','action:tell-customer-8801@1'])
pack('136_routed_by_the_book',evidence=_routed('by_the_book'))
pack('137_routed_incident',evidence=_routed('incident'))
# The router matched this complaint (about a festival offer) against the declared styles and found none: it says so in a row of its own.
pack('138_routed_unmatched',evidence=_routed('unmatched'))
# A new style is one more card and one reviewed replacement of the declaration: the older branches as they were, and one more. The two older cards are not touched.
pack('139_style_campaign',
     rules=[rule('R-STYLES@2','complaint_8801_closed',_STYLES+[_UNMATCHED,['styled_campaign','resolved_as_campaign']],
                 replaces='R-STYLES@1',source='reviewed/credit-ops-charter',styles=['run-the-book','incident','campaign'],unmatched=_FALLBACK),
            rule('R-STYLE-CAMPAIGN@1','resolved_as_campaign',[['offer_8801_checked','credit_8801_applied']],source='reviewed/style-card',
                 card=_card('campaign','T2 known-unknown','predictable','two-system ask','periodic','local workflow','the offer was checked and the credit applied','auto'))],
     methods=[method('check-offer-8801@1','offer_8801_checked',['complaint_8801_logged'],provider='ops-desk',cost={'compute':1,'money':0,'attention':0}),
              method('apply-credit-8801@1','credit_8801_applied',['offer_8801_checked'],provider='ops-desk',cost={'compute':1,'money':2,'attention':0})],
     grants=['action:check-offer-8801@1','action:apply-credit-8801@1'])
