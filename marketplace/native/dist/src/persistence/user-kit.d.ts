/**
 * user-kit — runtime persistence for founder-created Domains, Charters, Workflows.
 *
 * Storage layout (per-user, NOT shipped with plugin):
 *   $SUTRA_NATIVE_HOME/user-kit/domains/<id>.json
 *   $SUTRA_NATIVE_HOME/user-kit/charters/<id>.json
 *   $SUTRA_NATIVE_HOME/user-kit/workflows/<id>.json
 *
 * Default $SUTRA_NATIVE_HOME = ~/.sutra-native
 *
 * Every load round-trips through createDomain / createCharter / createWorkflow
 * so primitive validators run on disk content too — defense against drift if
 * a founder hand-edits the JSON.
 */
import { type Charter } from '../primitives/charter.js';
import { type Domain } from '../primitives/domain.js';
import { type Workflow } from '../primitives/workflow.js';
import { type TriggerSpec } from '../types/trigger-spec.js';
export interface UserKitOptions {
    /** Override storage root. Defaults to $SUTRA_NATIVE_HOME or ~/.sutra-native. */
    readonly home?: string;
    /** env override for testing. */
    readonly env?: NodeJS.ProcessEnv;
}
export declare function userKitRoot(opts?: UserKitOptions): string;
export declare function persistDomain(d: Domain, opts?: UserKitOptions): string;
export declare function loadDomain(id: string, opts?: UserKitOptions): Domain | null;
export declare function listDomains(opts?: UserKitOptions): Domain[];
export declare function persistCharter(c: Charter, opts?: UserKitOptions): string;
export declare function loadCharter(id: string, opts?: UserKitOptions): Charter | null;
export declare function listCharters(opts?: UserKitOptions): Charter[];
export declare function persistWorkflow(w: Workflow, opts?: UserKitOptions): string;
export declare function loadWorkflow(id: string, opts?: UserKitOptions): Workflow | null;
export declare function listWorkflows(opts?: UserKitOptions): Workflow[];
export declare function persistTrigger(t: TriggerSpec, opts?: UserKitOptions): string;
export declare function loadTrigger(id: string, opts?: UserKitOptions): TriggerSpec | null;
export declare function listTriggers(opts?: UserKitOptions): TriggerSpec[];
export interface UserKit {
    readonly domains: ReadonlyArray<Domain>;
    readonly charters: ReadonlyArray<Charter>;
    readonly workflows: ReadonlyArray<Workflow>;
    readonly triggers: ReadonlyArray<TriggerSpec>;
}
export declare function loadUserKit(opts?: UserKitOptions): UserKit;
//# sourceMappingURL=user-kit.d.ts.map