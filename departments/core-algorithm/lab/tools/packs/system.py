# The page builder (extensions/system.py, extensions/g2.py): its four packs. Authoring code, handed pack, fact, rule and method.
#
# 170  a goal recorded as not true (case 70): the order desk wrote the order down as not complete. The plan still asks the customer;
#      after a yes the replacement ships, and the stored row then contradicts what the rule derives. The page builder must not
#      call that waiting: its exhibit `order-recorded-open` is built from these packs.
# 171  the domain catalogue: the reviewed pack sets the page builder may pick from, in the words a person would use. Choosing a
#      domain for an ask is a judgement (an agent or a person makes it); the list is data, and it is closed. The kernel reads no
#      section of this pack: it is a pack so that it is authored, written and digested like every other reviewed input.
#      Every row is a recorded case (its packs are that case's packs): website = 28, order = 29, enquiry = 14, workflow-standard = 26.
# 172  the exhibits: rows that are NOT in the catalogue. Each shows what the builder says when it cannot say ready or waiting, and
#      each is a recorded case too: no plan (case 02), a plan that stops at a step (case 30), a yes after which every step ran and
#      the goal still does not hold (case 70), a yes after which the kernel has no plan left (case 71).
# 173  an order that closes on the customer's word (case 71). The desk recorded the order as not closed. It closes when a refund is
#      on record or when the customer confirms that the parcel arrived. The customer may be asked; no method may ask about a refund.
#      After a yes the kernel has no plan left, for two reasons: the confirmation closes the order while the desk's row says it is
#      not closed (EVIDENCE_CONFLICT, the reason the kernel names the run with), and the refund is still unknown (QUERY_EVIDENCE,
#      first in the order of the trace). A fact about the refund would unblock nothing; the page must name the conflict.
pack('170_recorded_open', evidence=[fact('order_complete', 'FALSE', source='fixture/order-desk', version='desk-1')])

_ORDER = {'order_complete': 'the order is complete', 'original_delivered': 'the original item is delivered', 'replacement_delivered': 'a replacement is delivered',
          'customer_approved': 'the customer has approved a replacement', 'original_stock': 'the original item is in stock', 'substitute_stock': 'a substitute is in stock',
          'ship-original@1': 'Ship the original item', 'ship-replacement@1': 'Ship the replacement', 'ask-customer-approval@1': 'Ask the customer'}

pack('171_domain_catalogue', domains=[
    {'id': 'website', 'title': 'Website', 'goal': 'site_live', 'say': 'a website for my organisation',
     'words': ['website', 'site', 'web', 'pages', 'page', 'landing', 'organisation', 'organization', 'online', 'homepage'],
     'packs': ['70_site_goal', '71_site_theory', '72_site_methods'],
     'labels': {'site_live': 'the website is live', 'site_checked': 'the site has been checked', 'pages_built': 'the pages are built',
                'content_written': 'the content is written', 'site_planned': 'the site is planned', 'brief_given': 'the owner has given a brief',
                'plan-site@1': 'Plan the site', 'write-content@1': 'Write the content', 'build-pages@1': 'Build the pages', 'check-site@1': 'Check the site'}},
    {'id': 'order', 'title': 'Order fulfilment', 'goal': 'order_complete', 'say': 'complete a customer order when the item is out of stock',
     'words': ['order', 'orders', 'deliver', 'delivery', 'replacement', 'ship', 'shipping', 'fulfil', 'fulfilment', 'stock', 'item'],
     'packs': ['00_goal', '01_domain', '02_methods', '04_admission', '80_ask_method'], 'labels': _ORDER},
    {'id': 'enquiry', 'title': 'Enquiry desk', 'goal': 'enquiry_complete', 'say': 'answer and store customer enquiries',
     'words': ['enquiry', 'enquiries', 'inquiry', 'inquiries', 'inbox', 'support', 'answer', 'store', 'privacy'],
     'packs': ['20_enquiry_goal', '21_enquiry_theory', '22_enquiry_methods', '23_enquiry_extra_knowledge', '24_enquiry_privacy'],
     'labels': {'enquiry_complete': 'the enquiry is handled', 'record_stored': 'the enquiry is stored', 'record_retrievable': 'the stored enquiry can be read back',
                'support_inbox_retrievable': 'the enquiry is in the support inbox', 'privacy_checked': 'the privacy check is done', 'enquiry_valid': 'the enquiry is valid',
                'store-enquiry@1': 'Store the enquiry', 'readback-enquiry@1': 'Read the enquiry back', 'check-privacy@1': 'Check privacy'}},
    {'id': 'workflow-standard', 'title': 'Workflow standard', 'goal': 'workflow_registrable', 'say': 'check a workflow against the standard',
     'words': ['workflow', 'workflows', 'standard', 'standards', 'registrable', 'checklist', 'check'],
     'packs': ['60_standard_goal', '61_standard_theory', '62_handwritten_evidence', '63_repair_method'],
     'labels': {'workflow_registrable': 'the workflow meets the standard', 'has_trigger': 'the workflow says what starts it',
                'every_step_has_check': 'every step carries a check of its own', 'has_overall_verify': 'the workflow says how the whole is verified',
                'add-step-checks@1': 'Add a check to every step'}},
])

pack('173_closed_on_confirmation', scope='orgA/closing', goals=['order_closed'],
     rules=[rule('R-CLOSE@1', 'order_closed', [['refund_recorded'], ['receipt_confirmed']])],
     evidence=[fact('order_closed', 'FALSE', source='fixture/order-desk', version='desk-1')],
     methods=[method('ask-customer-receipt@1', 'receipt_confirmed', [], provider='owner-channel', cost={'compute': 0, 'money': 0, 'attention': 1}, action='ask',
                     question='Did the parcel arrive?', ask_to='customer')],
     providers={'owner-channel': 2}, grants=['action:ask-customer-receipt@1'])

pack('172_domain_exhibits', domains=[
    {'id': 'order-nobody-may-ask', 'title': 'Order fulfilment, nobody may ask', 'goal': 'order_complete', 'say': 'complete a customer order when nobody may ask the customer',
     'words': ['order'], 'packs': ['00_goal', '01_domain', '02_methods'], 'labels': _ORDER},
    {'id': 'builder-without-constructor', 'title': 'Capability builder, constructor missing', 'goal': 'capability_candidate_created',
     'say': 'build a capability from components whose constructor is missing', 'words': ['capability'],
     'packs': ['30_build_goal', '31_build_theory', '82_components_without_constructor'],
     'labels': {'capability_candidate_created': 'a capability candidate is created', 'source_contract_reviewed': 'the source contract is reviewed',
                'component_validate': 'the validating component is ready', 'component_store': 'the storing component is ready', 'component_read': 'the reading component is ready',
                'validate-field@1': 'Validate the field', 'store-component@1': 'Store the component', 'read-component@1': 'Read the component',
                'construct-enquiry-candidate@1': 'Construct the candidate'}},
    {'id': 'order-recorded-open', 'title': 'Order fulfilment, recorded as not complete', 'goal': 'order_complete', 'say': 'complete a customer order the desk recorded as not complete',
     'words': ['order'], 'packs': ['00_goal', '01_domain', '02_methods', '04_admission', '80_ask_method', '170_recorded_open'], 'labels': _ORDER},
    {'id': 'order-closed-on-confirmation', 'title': 'Order closing, recorded as not closed', 'goal': 'order_closed',
     'say': 'close a customer order the desk recorded as open once the customer confirms the parcel', 'words': ['order'], 'packs': ['173_closed_on_confirmation'],
     'labels': {'order_closed': 'the order is closed', 'refund_recorded': 'a refund is on record', 'receipt_confirmed': 'the customer has confirmed that the parcel arrived',
                'ask-customer-receipt@1': 'Ask the customer'}},
])
