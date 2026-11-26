/**
 * Windows の extended-length path prefix (`\\?\`) を取り除く。
 *
 * Tauri の dialog::open() / drag-drop は Windows 上で `\\?\` 付き path を
 * 返すことがあり、そのままだと:
 *
 * - UI 表示で一般的な `E:\videos\...` 表記と一貫性が崩れる
 * - Rust 側 (`Path::is_file()` 等) で path 比較に支障が出るケースがある
 *
 * このため drop screen が `selectedVideoPath` に格納する前に正規化する。
 * `appStateStore.setSelectedVideoPath` が pipeline 上の strip ポイント。
 *
 * - `\\?\C:\foo` → `C:\foo`
 * - `\\?\UNC\server\share` → `\\server\share`
 * - prefix なしの path は素通し
 */
export function stripExtendedPathPrefix(p: string): string {
  if (p.startsWith('\\\\?\\UNC\\')) {
    return '\\\\' + p.slice('\\\\?\\UNC\\'.length);
  }
  if (p.startsWith('\\\\?\\')) {
    return p.slice('\\\\?\\'.length);
  }
  return p;
}

/**
 * 絶対 path を fileName (basename) と parentDir に分解する。
 * Windows `\\?\` 拡張長 prefix は内部で {@link stripExtendedPathPrefix} を通す。
 * セパレータ末尾 / セパレータなし / parentDir 空 (= drive root) の edge case
 * もすべて空文字列にフォールバックする (例外を投げない、UI 表示用)。
 *
 * #676 — 5 画面 (drop / detecting / complete / preview / export) のファイルパス
 * 表示で共通利用。詳細は docs/ui-interaction-spec.md §1.6 参照。
 *
 * 例:
 *  - "E:\\videos\\foo.mkv"  → { fileName: "foo.mkv",  parentDir: "E:\\videos" }
 *  - "/tmp/foo.mp4"         → { fileName: "foo.mp4",  parentDir: "/tmp" }
 *  - "\\\\?\\C:\\foo.mkv"   → { fileName: "foo.mkv",  parentDir: "C:" }
 *  - "foo.mkv"              → { fileName: "foo.mkv",  parentDir: "" }
 *  - ""                     → { fileName: "",         parentDir: "" }
 */
export function splitPath(absPath: string): { fileName: string; parentDir: string } {
  if (!absPath) return { fileName: '', parentDir: '' };
  const normalized = stripExtendedPathPrefix(absPath);
  const idx = Math.max(
    normalized.lastIndexOf('/'),
    normalized.lastIndexOf('\\'),
  );
  if (idx < 0) return { fileName: normalized, parentDir: '' };
  return {
    fileName: normalized.slice(idx + 1),
    parentDir: normalized.slice(0, idx),
  };
}
