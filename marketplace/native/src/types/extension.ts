/**
 * Workflow extension seam — M4.5 (D4 §7).
 *
 * D-NS-9 founder default (b) applied per codex P1.2: only the D4-grounded
 * `extension_ref` ships in v1.0. The 4 candidate seams (`metadata`,
 * `schema_version`, `required_capabilities`, `discipline_tag`) defer to v1.x
 * case-by-case.
 *
 * v1.0 enforcement (D4 §7.3): `extension_ref` MUST be null on every shipped
 * Workflow. The format check (when v1.x non-null) is the regex
 * `/^ext-[a-z0-9-]+$/`. The "must be null in v1.0" gate lives at terminal_check
 * as forbidden coupling F-N (M4.9 chunk 2).
 *
 * Spec source:
 * - holding/research/2026-04-29-native-d4-primitives-composition-spec.md §7
 * - holding/plans/native-v1.0/M4-schemas-edges.md §M4.5
 */

import { z } from 'zod'

/**
 * Extension reference id pattern: `ext-<lowercase-alphanumeric-with-hyphens>`.
 * Reserved for v1.x; v1.0 enforcement is null-only.
 */
export const EXTENSION_REF_PATTERN = /^ext-[a-z0-9-]+$/

/**
 * ExtensionRefSchema — `string | null`.
 *
 * - `null` (default) accepted in every version
 * - non-null string MUST match `EXTENSION_REF_PATTERN`; v1.0 terminal_check
 *   additionally requires null (forbidden coupling F-N)
 */
export const ExtensionRefSchema = z.union([
  z.string().regex(EXTENSION_REF_PATTERN),
  z.null(),
])

export type ExtensionRef = z.infer<typeof ExtensionRefSchema>

/**
 * Predicate: is this value a valid ExtensionRef shape (null OR `ext-<id>`)?
 */
export function isValidExtensionRef(v: unknown): v is ExtensionRef {
  return ExtensionRefSchema.safeParse(v).success
}
