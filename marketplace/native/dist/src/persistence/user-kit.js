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
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { createCharter } from '../primitives/charter.js';
import { createDomain } from '../primitives/domain.js';
import { createWorkflow } from '../primitives/workflow.js';
export function userKitRoot(opts = {}) {
    const env = opts.env ?? process.env;
    if (opts.home)
        return opts.home;
    if (env.SUTRA_NATIVE_HOME)
        return env.SUTRA_NATIVE_HOME;
    const home = env.HOME ?? '/tmp';
    return `${home}/.sutra-native`;
}
function entityDir(kind, opts = {}) {
    return join(userKitRoot(opts), 'user-kit', kind);
}
function ensureDir(dir) {
    mkdirSync(dir, { recursive: true });
}
function writeJson(path, value) {
    writeFileSync(path, JSON.stringify(value, null, 2) + '\n', { encoding: 'utf8' });
}
function readJson(path) {
    return JSON.parse(readFileSync(path, 'utf8'));
}
// ---------------------------------------------------------------------------
// Domain
// ---------------------------------------------------------------------------
export function persistDomain(d, opts = {}) {
    const dir = entityDir('domains', opts);
    ensureDir(dir);
    const path = join(dir, `${d.id}.json`);
    writeJson(path, d);
    return path;
}
export function loadDomain(id, opts = {}) {
    const path = join(entityDir('domains', opts), `${id}.json`);
    if (!existsSync(path))
        return null;
    return createDomain(readJson(path));
}
export function listDomains(opts = {}) {
    const dir = entityDir('domains', opts);
    if (!existsSync(dir))
        return [];
    return readdirSync(dir)
        .filter((f) => f.endsWith('.json'))
        .map((f) => createDomain(readJson(join(dir, f))));
}
// ---------------------------------------------------------------------------
// Charter
// ---------------------------------------------------------------------------
export function persistCharter(c, opts = {}) {
    const dir = entityDir('charters', opts);
    ensureDir(dir);
    const path = join(dir, `${c.id}.json`);
    writeJson(path, c);
    return path;
}
export function loadCharter(id, opts = {}) {
    const path = join(entityDir('charters', opts), `${id}.json`);
    if (!existsSync(path))
        return null;
    return createCharter(readJson(path));
}
export function listCharters(opts = {}) {
    const dir = entityDir('charters', opts);
    if (!existsSync(dir))
        return [];
    return readdirSync(dir)
        .filter((f) => f.endsWith('.json'))
        .map((f) => createCharter(readJson(join(dir, f))));
}
// ---------------------------------------------------------------------------
// Workflow
// ---------------------------------------------------------------------------
export function persistWorkflow(w, opts = {}) {
    const dir = entityDir('workflows', opts);
    ensureDir(dir);
    const path = join(dir, `${w.id}.json`);
    writeJson(path, w);
    return path;
}
export function loadWorkflow(id, opts = {}) {
    const path = join(entityDir('workflows', opts), `${id}.json`);
    if (!existsSync(path))
        return null;
    return createWorkflow(readJson(path));
}
export function listWorkflows(opts = {}) {
    const dir = entityDir('workflows', opts);
    if (!existsSync(dir))
        return [];
    return readdirSync(dir)
        .filter((f) => f.endsWith('.json'))
        .map((f) => createWorkflow(readJson(join(dir, f))));
}
export function loadUserKit(opts = {}) {
    return {
        domains: listDomains(opts),
        charters: listCharters(opts),
        workflows: listWorkflows(opts),
    };
}
//# sourceMappingURL=user-kit.js.map