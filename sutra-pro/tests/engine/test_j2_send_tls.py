"""The STARTTLS certificate check of `engine/j2_send.py` (D248): the system store, verified, and a trusted certificate may end the chain."""
import ssl

from sutra_app.engine import j2_send


def test_starttls_lets_a_trusted_certificate_end_the_chain_and_still_verifies():
    context = j2_send.tls_context()
    assert context.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
