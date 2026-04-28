/**
 * #569 -- derive a per-video output directory for `allaganeye detect`.
 *
 * We don't ship a "where do I put the metadata.json" dialog yet, so the
 * GUI uses a deterministic sibling-of-the-video convention. Given
 * ``C:/videos/2026-04-08 21-14-05.mkv`` we produce
 * ``C:/videos/2026-04-08 21-14-05_allaganeye``.
 *
 * The result is always an absolute path with forward slashes (the CLI
 * accepts both, and forward slashes round-trip through Tauri / Rust
 * cleanly on Windows). Trailing slashes are stripped so the path can
 * be combined with ``metadata.json`` via simple string concatenation
 * without producing a double-slash.
 */
export function deriveDetectOutputDir(videoPath: string): string {
  const normalized = videoPath.replace(/\\/g, '/').replace(/\/+$/, '');
  const lastSlash = normalized.lastIndexOf('/');
  const dir = lastSlash >= 0 ? normalized.slice(0, lastSlash) : '.';
  const file = lastSlash >= 0 ? normalized.slice(lastSlash + 1) : normalized;
  const dot = file.lastIndexOf('.');
  const stem = dot > 0 ? file.slice(0, dot) : file;
  return `${dir}/${stem}_allaganeye`;
}

/**
 * #569 -- canonical metadata.json location inside an output dir.
 *
 * Mirrors the CLI's hard-coded ``<output_dir>/metadata.json`` filename
 * so the frontend can preview the destination on the detecting screen
 * before the subprocess writes the file.
 */
export function metadataPathFor(outputDir: string): string {
  const normalized = outputDir.replace(/\\/g, '/').replace(/\/+$/, '');
  return `${normalized}/metadata.json`;
}
