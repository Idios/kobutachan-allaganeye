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
