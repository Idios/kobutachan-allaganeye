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
 * `dir` と `name` を OS-appropriate なセパレータで連結する。
 *
 * separator 推定ルール:
 * - dir に `\` のみ含まれる (Windows native) → `\` で連結
 * - それ以外 (`/` 含む / 両方混在 / 分離なし) → `/` を優先
 * - dir が `/` または `\` で終わっている場合は重複させない
 *
 * Windows extended-length path や POSIX path、混在パスのいずれでも一貫した
 * 動作になる。ExportScreen の `outputPath` 組み立てに使用。
 */
export function joinPath(dir: string, name: string): string {
  const separator = dir.includes('\\') && !dir.includes('/') ? '\\' : '/';
  if (dir.endsWith('/') || dir.endsWith('\\')) return dir + name;
  return dir + separator + name;
}
