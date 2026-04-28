// Re-export shim for the auto-generated Metadata types (#612).
//
// The generated declarations live in `metadata.generated.ts` (sourced
// from `schemas/metadata.schema.json` via `python scripts/codegen/generate.py`).
// Existing GUI code imports `Match` / `Metadata` from this module and
// expects them to include the in-memory edit fields (`name`,
// `type_override`, `edited`) -- those live only in the GUI store and
// metadata.draft.json (zod passthrough), not in metadata.json proper.
//
// Shape extension lives here so the generated file stays a faithful
// projection of the JSON Schema. `normalizeForPersistence` strips the
// edit fields back out before write (see metadataStore.ts).

import type {
  Match as PersistedMatch,
  Metadata as PersistedMetadata,
} from './metadata.generated';

export type {
  BrightnessSamples,
  DetectionParams,
  Gap,
  MetadataWarning,
  SystemInfo,
} from './metadata.generated';

/**
 * The persisted, JSON-Schema-conformant Match shape (no edit fields).
 * Re-exported for callers that explicitly want the `metadata.json`
 * contract type (e.g. tests asserting normalize output).
 */
export type { Match as PersistedMatch } from './metadata.generated';

export type MatchType = 'fl_match' | 'unknown';

export type TypeOverride = MatchType | 'skip';

export type WarningSeverity = 'info' | 'warn' | 'error';

/**
 * Match plus GUI-only edit fields. The default `Match` type used
 * throughout the GUI; persistence strips the edit fields back out.
 */
export interface Match extends PersistedMatch {
  name?: string;
  type_override?: TypeOverride;
  edited?: { start_time: number; end_time: number };
}

/**
 * Backward-compat alias. Some screens explicitly import this name to
 * make the editable-vs-persisted distinction obvious; new code can
 * pick whichever reads better.
 */
export type EditableMatch = Match;

export interface Metadata extends Omit<PersistedMetadata, 'matches'> {
  matches: Match[];
}
