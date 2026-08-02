/**
 * 出力ファイル名テンプレートの展開 (export / minimap 共有)。
 *
 * CLI 側の正は `allaganeye/export/pool.py` の `_format_filename` /
 * `_format_start_for_filename`。GUI の一覧に出す「これから書き出される名前」は
 * CLI が実際に書く名前と一致していなければ意味がないので、両者は同じトークン
 * 集合・同じ format 規則を保つこと。
 *
 * #932: 元は ExportScreen.tsx のローカル関数だった。MinimapScreen が
 * ExportScreen を mirror した際に展開処理を取りこぼし、一覧が CLI の生成しない
 * `match_NNN_minimap.mp4` を表示していたため、共有 util に切り出した。
 */

/**
 * #545 review #8 (2026-04-25): filename 用の `{start}` 変数を `MM-SS` /
 * `H-MM-SS` 形式に format する。`fmtTime` の `:` を `-` に置換した形と等価
 * (Windows filename で `:` が使えないため)。
 *
 * 例:
 * - 0       → `00-00`
 * - 915.5   → `15-15`
 * - 5021.5  → `1-23-41`
 */
export function formatStartForFilename(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    seconds = 0;
  }
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}-${String(m).padStart(2, '0')}-${String(s).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}-${String(s).padStart(2, '0')}`;
}

/**
 * name pattern を展開して 1 match 分の出力ファイル名を返す。
 *
 * トークン: `{idx:03}` / `{idx}` / `{type}` / `{start}` / `{date}`
 * (`docs/cli-spec.md` の `--name-pattern` と同一集合)。
 *
 * `{idx:03}` を `{idx}` より先に置換するのは、`{idx}` を先にすると
 * `{idx:03}` の中の `{idx` が食われて `2:03}` のような壊れた名前になるため。
 */
export function formatMatchFilename(
  pattern: string,
  index: number,
  type: string,
  startSec: number,
): string {
  const startDisplay = formatStartForFilename(startSec);
  const today = new Date().toISOString().slice(0, 10);
  return pattern
    .replace(/\{idx:03\}/g, String(index).padStart(3, '0'))
    .replace(/\{idx\}/g, String(index))
    .replace(/\{type\}/g, type)
    .replace(/\{start\}/g, startDisplay)
    .replace(/\{date\}/g, today);
}
