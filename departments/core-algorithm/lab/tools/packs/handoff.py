# 0.18.0-handoff: work handed to a hand and checked by a separate checker, with tries. The standing example is a lender.
# Its letters desk must get a collections letter for loan L-17 queued for sending. Queueing needs a drafted letter. A model drafts
# it, outside the kernel, and the letter counts as drafted only when a checker that reads the loan book says so.
#   the hand      model:letter-drafter         does the work; never says that it is done
#   the checker   checker:loan-book            reads the letter and the loan book; its rows are the evidence
#   a second hand person:collections-officer   dearer in attention; the kernel takes it when the model has no slot left
# Ruling R35 of the program: the need is first stated with the parts the lab already has (packs 215 to 217 and the look of case 85),
# and what the algorithm makes of it is recorded (the sequence handoff_existing). Packs 211 and 214 use the one part this version adds.
HAND, CHECKER, OFFICER = 'model:letter-drafter', 'checker:loan-book', 'person:collections-officer'
WORK = 'Draft the collections letter for loan L-17: name the borrower, the loan and the amount overdue.'

# The desk. Its goal is the queued letter; the one method it has of its own queues a letter that is drafted. Nothing here says who drafts.
# It saves its people's attention first, then money, then tokens.
pack('210_letters_desk', scope='lendco/collections-letters', goals=['letter_queued'],
     budget={'compute': 10, 'money': 5, 'attention': 3}, preference=['attention', 'money', 'compute'],
     methods=[method('queue-collections-letter@1', 'letter_queued', ['letter_drafted'], cost={'compute': 1, 'money': 0, 'attention': 0})],
     providers={'local-provider': 4}, grants=['action:queue-collections-letter@1'])
# The letter is handed to the model. Each try costs two tokens (a unit of the budget line `compute`) and takes one slot of the model's
# provider, which the kernel never returns: the capacity stated here, 3, is the number of tries.
pack('211_hand_to_model',
     methods=[method('hand-letter-to-model@1', 'letter_drafted', ['loan_on_book'], provider='letter-model', cost={'compute': 2, 'money': 0, 'attention': 0},
                     action='handoff', handoff_to=HAND, instruction=WORK, verified_by=CHECKER)],
     providers={'letter-model': 3}, grants=['action:hand-letter-to-model@1'])
# The loan is on the book. In a case this row is a fixture; in the sequence handoff_letter the checker reads the book and states the row itself.
pack('212_book_read', evidence=[fact('loan_on_book', 'TRUE', source=CHECKER, version='book-fixture')])
# The model has no slot left (its tries are used up).
pack('213_model_spent', providers={'letter-model': 0})
# A second way to the same letter: a person. It costs attention, which the desk saves first, so the model is taken while it has a slot.
pack('214_hand_to_officer',
     methods=[method('hand-letter-to-officer@1', 'letter_drafted', ['loan_on_book'], provider='collections-officer', cost={'compute': 0, 'money': 0, 'attention': 1},
                     action='handoff', handoff_to=OFFICER, instruction=WORK, verified_by=CHECKER)],
     providers={'collections-officer': 1}, grants=['action:hand-letter-to-officer@1'])
# ---- The same need with the parts the lab had before this version (ruling R35): the ask, and no step at all (pack 210 with 212 alone).
# An ask put to the doer: the model is asked to draft the letter and to say when it is done.
pack('215_ask_the_drafter',
     methods=[method('ask-drafter-for-letter@1', 'letter_drafted', ['loan_on_book'], provider='drafter-channel', cost={'compute': 0, 'money': 0, 'attention': 1}, action='ask',
                     question='Draft the collections letter for loan L-17 and say when it is done.', ask_to=HAND)],
     providers={'drafter-channel': 3}, grants=['action:ask-drafter-for-letter@1'])
# An ask put to the checker: the checker is asked whether the letter in the folder matches the loan book.
pack('216_ask_the_checker',
     methods=[method('ask-checker-about-letter@1', 'letter_drafted', ['loan_on_book'], provider='checker-channel', cost={'compute': 0, 'money': 0, 'attention': 1}, action='ask',
                     question='Does the letter drafted for loan L-17 match the loan book?', ask_to=CHECKER)],
     providers={'checker-channel': 3}, grants=['action:ask-checker-about-letter@1'])
# Three tries written as three asks to the checker under one rule: the letter is drafted when the first, the second or the third draft passes.
pack('217_three_asks',
     rules=[rule('R-LETTER-TRIES@1', 'letter_drafted', [['draft_1_passes'], ['draft_2_passes'], ['draft_3_passes']], source='reviewed/letters-desk')],
     methods=[method(f'ask-checker-about-draft-{n}@1', f'draft_{n}_passes', ['loan_on_book'], provider='checker-channel', cost={'compute': 0, 'money': 0, 'attention': 1}, action='ask',
                     question=f'Try {n} of 3: does the letter drafted for loan L-17 match the loan book?', ask_to=CHECKER) for n in (1, 2, 3)],
     providers={'checker-channel': 3}, grants=[f'action:ask-checker-about-draft-{n}@1' for n in (1, 2, 3)])
