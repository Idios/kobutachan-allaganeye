/**
 * #814 -- single definition of the metadata match-boundary write invariant.
 *
 * A match must have a strictly positive duration: `end_time > start_time`.
 * The zod MatchSchema refine is lenient on read (`end >= start`), but the GUI
 * must never *write* a degenerate or inverted boundary — `end < start` makes
 * metadata.json unreadable on reload (audit P1-2) and `end == start` produces
 * an empty clip. Used by both `metadataStore.runApply` (apply-time block) and
 * `PreviewScreen` (the [適用] button disable + edit clamp).
 */
export function isBoundaryValid(startTime: number, endTime: number): boolean {
  return (
    Number.isFinite(startTime) &&
    Number.isFinite(endTime) &&
    endTime > startTime
  );
}
