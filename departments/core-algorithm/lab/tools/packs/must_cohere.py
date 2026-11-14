# Must-cohere (matrix row R55), as far as the kernel holds it: a verified FALSE row on the goal while evidence closes one branch of the goal's rule.
# Loaded after 00_goal and 01_domain. The courier's scan (version 2) replaces 01_domain's FALSE row on original_delivered, so ONE part of the order rule
# reads TRUE; the other branch (replacement_delivered) stays FALSE and has no method here. The order desk's verified row says the order is not complete.
# What the kernel does with the two rows: it names the conflict on the goal (EVIDENCE_CONFLICT) and offers no plan. It does not weigh one row against the other.
pack('100_delivered_but_open',
     evidence=[fact('original_delivered','TRUE',source='fixture/courier-scan',version='2'),
               fact('order_complete','FALSE',source='fixture/order-desk',version='1')])
