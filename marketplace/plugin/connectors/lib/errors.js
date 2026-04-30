/**
 * Sutra Connectors — Typed error classes
 * Frozen by LLD §2.8.
 */
export class ConnectorError extends Error {
    code;
    constructor(message, code) {
        super(message);
        this.name = 'ConnectorError';
        this.code = code;
    }
}
export class ManifestError extends ConnectorError {
    code;
    constructor(message, code) {
        super(message, code);
        this.name = 'ManifestError';
        this.code = code;
    }
}
export class PolicyDeniedError extends ConnectorError {
    decision;
    constructor(message, decision) {
        super(message, 'policy-denied');
        this.name = 'PolicyDeniedError';
        this.decision = decision;
    }
}
export class StalePolicyError extends ConnectorError {
    constructor(message) {
        super(message, 'stale-policy');
        this.name = 'StalePolicyError';
    }
}
export class ApprovalRequiredError extends ConnectorError {
    request;
    constructor(message, request) {
        super(message, 'approval-required');
        this.name = 'ApprovalRequiredError';
        this.request = request;
    }
}
export class ApprovalTokenExpiredError extends ConnectorError {
    constructor(message) {
        super(message, 'approval-token-expired');
        this.name = 'ApprovalTokenExpiredError';
    }
}
export class ForbiddenComposioApiError extends ConnectorError {
    api;
    constructor(api) {
        super(`Composio API '${api}' is forbidden by Sutra L1 control-plane discipline. ` +
            `Only authenticate, executeTool, isAuthenticated are permitted.`, 'forbidden-composio-api');
        this.name = 'ForbiddenComposioApiError';
        this.api = api;
    }
}
export class IdempotencyKeyRequiredError extends ConnectorError {
    constructor(message) {
        super(message, 'idempotency-key-required');
        this.name = 'IdempotencyKeyRequiredError';
    }
}
export class PayloadTooLargeError extends ConnectorError {
    bytes;
    maxBytes;
    constructor(message, bytes, maxBytes) {
        super(message, 'payload-too-large');
        this.name = 'PayloadTooLargeError';
        this.bytes = bytes;
        this.maxBytes = maxBytes;
    }
}
export class CredentialNotFoundError extends ConnectorError {
    connector;
    constructor(connector) {
        super(`No credential found for connector: ${connector}`, 'credential-not-found');
        this.name = 'CredentialNotFoundError';
        this.connector = connector;
    }
}
export class SecretStoreSafetyError extends ConnectorError {
    constructor(message) {
        super(message, 'secret-store-safety');
        this.name = 'SecretStoreSafetyError';
    }
}
export class SecretStoreTimeoutError extends ConnectorError {
    constructor(message) {
        super(message, 'secret-store-timeout');
        this.name = 'SecretStoreTimeoutError';
    }
}
export class SecretStoreDecryptError extends ConnectorError {
    constructor(message) {
        super(message, 'secret-store-decrypt');
        this.name = 'SecretStoreDecryptError';
    }
}
export class AbortError extends ConnectorError {
    constructor(message) {
        super(message, 'aborted');
        this.name = 'AbortError';
    }
}
