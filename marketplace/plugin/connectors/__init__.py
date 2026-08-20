"""Sutra connector platform.

A connector is a first-class primitive: a persisted, permission-bearing,
auditable relationship between one Sutra operator and one external account,
with a lifecycle independent of the operator's Sutra session.

OAuth is the mechanism by which a connector is established. It is not the
connector.

Design pack: design/00-INDEX.md
Decision of record: ../../../os/decisions/ADR-034-connector-token-ownership.md
"""
__version__ = "0.1.0"
