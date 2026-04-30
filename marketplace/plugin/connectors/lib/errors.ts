/**
 * Sutra Connectors — Typed error classes
 * Frozen by LLD §2.8.
 */

import type { PolicyDecision, FounderApprovalRequest } from './types.js';

export class ConnectorError extends Error {
  readonly code: string;
  constructor(message: string, code: string) {
    super(message);
    this.name = 'ConnectorError';
    this.code = code;
  }
}

export class ManifestError extends ConnectorError {
  override readonly code:
    | 'malformed'
    | 'invalid-capability'
    | 'missing-field'
    | 'overbroad-capability'
    | 'schema-version';
  constructor(
    message: string,
    code: ManifestError['code'],
  ) {
    super(message, code);
    this.name = 'ManifestError';
    this.code = code;
  }
}

export class PolicyDeniedError extends ConnectorError {
  readonly decision: PolicyDecision;
  constructor(message: string, decision: PolicyDecision) {
    super(message, 'policy-denied');
    this.name = 'PolicyDeniedError';
    this.decision = decision;
  }
}

export class StalePolicyError extends ConnectorError {
  constructor(message: string) {
    super(message, 'stale-policy');
    this.name = 'StalePolicyError';
  }
}

export class ApprovalRequiredError extends ConnectorError {
  readonly request: FounderApprovalRequest;
  constructor(message: string, request: FounderApprovalRequest) {
    super(message, 'approval-required');
    this.name = 'ApprovalRequiredError';
    this.request = request;
  }
}

export class ApprovalTokenExpiredError extends ConnectorError {
  constructor(message: string) {
    super(message, 'approval-token-expired');
    this.name = 'ApprovalTokenExpiredError';
  }
}

export class ForbiddenComposioApiError extends ConnectorError {
  readonly api: string;
  constructor(api: string) {
    super(
      `Composio API '${api}' is forbidden by Sutra L1 control-plane discipline. ` +
        `Only authenticate, executeTool, isAuthenticated are permitted.`,
      'forbidden-composio-api',
    );
    this.name = 'ForbiddenComposioApiError';
    this.api = api;
  }
}

export class IdempotencyKeyRequiredError extends ConnectorError {
  constructor(message: string) {
    super(message, 'idempotency-key-required');
    this.name = 'IdempotencyKeyRequiredError';
  }
}

export class PayloadTooLargeError extends ConnectorError {
  readonly bytes: number;
  readonly maxBytes: number;
  constructor(message: string, bytes: number, maxBytes: number) {
    super(message, 'payload-too-large');
    this.name = 'PayloadTooLargeError';
    this.bytes = bytes;
    this.maxBytes = maxBytes;
  }
}

export class CredentialNotFoundError extends ConnectorError {
  readonly connector: string;
  constructor(connector: string) {
    super(`No credential found for connector: ${connector}`, 'credential-not-found');
    this.name = 'CredentialNotFoundError';
    this.connector = connector;
  }
}

export class SecretStoreSafetyError extends ConnectorError {
  constructor(message: string) {
    super(message, 'secret-store-safety');
    this.name = 'SecretStoreSafetyError';
  }
}

export class SecretStoreTimeoutError extends ConnectorError {
  constructor(message: string) {
    super(message, 'secret-store-timeout');
    this.name = 'SecretStoreTimeoutError';
  }
}

export class SecretStoreDecryptError extends ConnectorError {
  constructor(message: string) {
    super(message, 'secret-store-decrypt');
    this.name = 'SecretStoreDecryptError';
  }
}

export class AbortError extends ConnectorError {
  constructor(message: string) {
    super(message, 'aborted');
    this.name = 'AbortError';
  }
}
