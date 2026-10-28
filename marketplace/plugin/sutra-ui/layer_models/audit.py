"""Audit's records (A1.13b): a reading, its items, a finding and a spot check."""
from pydantic import ConfigDict
import layer_consts as K
from .base import Open
from .common import keep_order, WORD, NULLABLE, T, I, B, E, L, IdFinding, IdItem, Name


class AuditReadingItem(Open):
    __def__ = 'audit.reading_item'
    id: IdItem
    subject: T(200)
    claim: T(600)
    evidence: T(1000)
    method: E('code', 'model')
    verdict: E(*K.ITEM_VERDICTS)
    severity: E(*K.SEVERITIES)


class AuditFinding(Open):
    __def__ = 'audit.finding'
    id: IdFinding
    severity: E(*K.SEVERITIES)
    claim: T(600)
    where: T(200)
    item: NULLABLE(IdItem) = None
    went_to: NULLABLE(E('Identity', 'Adaptation', 'you')) = None
    ask: NULLABLE(T(40)) = None
    at: T(40) = None


class AuditReading(Open):
    __def__ = 'audit.reading'
    model_config = ConfigDict(json_schema_extra=keep_order(('schema_version', 'id', 'v', 'artifact', 'cycle_id', 'round', 'read', 'why_not_read', 'items', 'findings', 'at')))
    id: WORD('^r-[0-9a-f]{8}$', 10)
    v: I(1)
    artifact: Name
    read: B
    items: L(AuditReadingItem)
    at: T(40)
    schema_version: I(1) = None
    cycle_id: NULLABLE(T(80)) = None
    round: NULLABLE(I(1)) = None
    why_not_read: NULLABLE(T(300)) = None
    findings: L(AuditFinding) = None


class AuditSpotCheckChecksItem(Open):
    __inline__ = True
    check: T(80)
    ok: B
    why: T(300)


class AuditSpotCheck(Open):
    __def__ = 'audit.spot_check'
    model_config = ConfigDict(json_schema_extra=keep_order(('schema_version', 'id', 'at', 'minute', 'checks', 'findings')))
    id: T(40)
    at: T(40)
    checks: L(AuditSpotCheckChecksItem)
    findings: L(AuditFinding)
    schema_version: I(1) = None
    minute: I(0, 1439) = None


DEFINES = {
    'audit.reading_item': AuditReadingItem,
    'audit.finding': AuditFinding,
    'audit.reading': AuditReading,
    'audit.spot_check': AuditSpotCheck,
}
__all__ = [
    'AuditFinding', 'AuditReading', 'AuditReadingItem', 'AuditSpotCheck', 'DEFINES',
]
