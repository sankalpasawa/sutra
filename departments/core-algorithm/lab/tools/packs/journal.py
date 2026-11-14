# Memory across runs (the journal version, matrix gap 1: rows R07 and R11). Two packs for the recorded sequences; the kernel is not changed.
# 140: the owner states the three levels again after a shipment (a top-up). Handed over twice, the kernel takes it twice
# (case 60); the journal's door lets a pack id in once.
pack('140_levels_restated', budget={'compute': 10, 'money': 10, 'attention': 3})
# 141: the ask of pack 80 under its own method id, with a question that holds three line marks: U+2028 after the first
# sentence, U+2029 after the second, U+0085 at the end (made with chr, so this file holds no character that cannot be seen).
# The kernel takes the question as it takes any text; a reader that cuts text at every line mark would cut the journal
# entry that holds it.
pack('141_ask_with_line_marks',
     methods=[method('ask-customer-approval@2', 'customer_approved', [], provider='owner-channel', cost={'compute': 0, 'money': 0, 'attention': 1}, action='ask',
                     question='May we send a replacement?' + chr(0x2028) + 'The item is out of stock.' + chr(0x2029) + 'Reply yes or no.' + chr(0x85), ask_to='customer')],
     providers={'owner-channel': 2}, grants=['action:ask-customer-approval@2'])
