/**
 * name-pattern プレビュー sandbox 検証 (#964)。
 *
 * CLI 側 (`allaganeye/export/pool.py` の `_render_and_sandbox` /
 * `resolve_output_paths`、いわゆる「層 1」) の検証を TypeScript へ移植した
 * **プレビュー用 mirror**。GUI は出力一覧に「これから書き出される名前」を出すため、
 * 書き出し時に exit 5 で拒否される名前をプレビュー時点で警告しなければならない。
 *
 * 移植の射程は層 1 のみ:
 * - 層 2 (worker 再検証 + source hardlink の inode ガード) と層 3 (post-write の
 *   `(st_dev, st_ino)` 突合) は実ファイルの identity を扱うためブラウザでは
 *   再現できない (docs/output-spec.md §ユーザーに提示するパスの契約 参照)。
 * - 本 module は**警告表示のみ**で、書き出しをブロックしない。最終 gate は CLI 側の
 *   exit 5 のまま (本 module の字句解決は symlink 等の実 FS 状態を再現しないため)。
 *
 * Windows の path 規則を無条件に適用する: 本ツールの対応 platform は Windows のみで、
 * 実際に書き出しを実行する CLI は Windows 上で動く (既存 `utils/path.ts` /
 * `filename.ts` も同じ前提)。
 */

import { formatMatchFilename } from './filename';
import { stripExtendedPathPrefix } from './path';

/** Windows 予約デバイス名 (#937 (a) と同一集合)。bare 名のみ予約 (拡張子付きは可)。 */
const WIN32_RESERVED_NAMES = new Set(
  [
    'CON',
    'PRN',
    'AUX',
    'NUL',
    ...Array.from({ length: 9 }, (_, i) => `COM${i + 1}`),
    ...Array.from({ length: 9 }, (_, i) => `LPT${i + 1}`),
  ].map((n) => n.toLowerCase()),
);

export type NamePatternIssueKind =
  | 'escape'
  | 'overwriteSource'
  | 'invalidWindowsName'
  | 'collision';

export interface NamePatternIssue {
  kind: NamePatternIssueKind;
  /** ユーザー向けの 1 文 (修正の指針を含む)。 */
  message: string;
  /** 問題のある rendered ファイル名 (先頭 1 件)。 */
  sampleName: string;
}

/** 検証対象の 1 行。GUI の `countedMatches` (実際に CLI へ渡る集合) に一致させる。 */
export interface SandboxRow {
  index: number;
  /** metadata `matches[].type` — `{type}` トークンへ verbatim 展開される。 */
  type: string;
  /** 境界調整済みなら edited 側の start (秒)。 */
  startSec: number;
}

/**
 * 字句解決した Windows canonical パス。
 *
 * - `drive`: `c:` (ドライブレター、lowercase) / `//server/share` (UNC) / `''` (無し)
 * - `rooted`: drive 直後の root 区切り付き絶対 (`c:/x`) / UNC は常に true
 * - `parts`: `.` / 空 segment を除去済みの**未解決** segment 列。`..` は winJoin
 *   が base と連結した後に pop するため、ここでは保持する
 */
interface WinPath {
  drive: string;
  rooted: boolean;
  parts: string[];
}

function parseWinPath(input: string): WinPath {
  const p = stripExtendedPathPrefix(input).replace(/\\/g, '/');
  let drive = '';
  let rooted = false;
  let rest = p;

  const unc = p.match(/^(\/\/[^/]+\/[^/]+)(?:\/(.*))?$/);
  if (unc) {
    // UNC: //server/share 以降を drive として扱う
    drive = unc[1].toLowerCase();
    rest = unc[2] ?? '';
    rooted = true;
  } else {
    const driveMatch = p.match(/^([a-zA-Z]):(.*)$/);
    if (driveMatch) {
      drive = `${driveMatch[1].toLowerCase()}:`;
      rest = driveMatch[2] ?? '';
      rooted = rest.startsWith('/');
      if (rooted) rest = rest.slice(1);
    } else if (p.startsWith('/')) {
      rooted = true;
      rest = p.slice(1);
    }
  }

  const parts = rest.split('/').filter((s) => s !== '' && s !== '.');
  return { drive, rooted, parts };
}

/** `..` を pop 解決する (root より上は root に留まる)。 */
function collapse(parts: string[]): string[] {
  const out: string[] = [];
  for (const seg of parts) {
    if (seg === '..') {
      if (out.length > 0) out.pop();
    } else {
      out.push(seg);
    }
  }
  return out;
}

/** ntpath.join に近い drive 規則で base へ child (rendered 名) を連結する。 */
function winJoin(base: WinPath, childStr: string): WinPath {
  const child = parseWinPath(childStr);
  if (child.drive !== '') {
    // drive を持つ child: drive が異なれば child が全て勝つ (CLI resolve と同じ)。
    // 同じ drive なら root 付き絶対は置換、drive-relative (`c:x`) は追記
    // (pool.py の premise test と同じく sandbox 内に留まる)。
    if (child.drive !== base.drive) return { ...child, parts: collapse(child.parts) };
    if (child.rooted) return { ...child, parts: collapse(child.parts) };
    return { ...base, parts: collapse(base.parts.concat(child.parts)) };
  }
  if (child.rooted) {
    // `\x` / `/x`: base の drive 上で root から置換
    return { ...base, parts: collapse(child.parts) };
  }
  // 相対 child: base に連結してから `..` を解決する (先頭 `..` は base を遡る)
  return { ...base, parts: collapse(base.parts.concat(child.parts)) };
}

/** CLI の containment 判定 (大小文字無視の prefix、同一は拒否対象)。 */
function isStrictlyInside(root: WinPath, candidate: WinPath): boolean {
  if (root.drive !== candidate.drive) return false;
  if (candidate.parts.length <= root.parts.length) return false;
  return root.parts.every((seg, i) => seg.toLowerCase() === candidate.parts[i].toLowerCase());
}

/** case-insensitive path 等価 (CLI の `resolved == source` に相当。fold しない)。 */
function samePathCaseInsensitive(a: WinPath, b: WinPath): boolean {
  if (a.drive !== b.drive || a.parts.length !== b.parts.length) return false;
  return a.parts.every((seg, i) => seg.toLowerCase() === b.parts[i].toLowerCase());
}

/** component 単位の identity fold (pool.py `_identity_key` の TS mirror)。 */
function identityKey(candidate: WinPath): string {
  return candidate.parts
    .map((part) => {
      const trimmed = part.replace(/[. ]+$/, '');
      return (trimmed || part).toLowerCase();
    })
    .join('/');
}

/** per-row 検証結果。collision 判定のため通過行は identity を保持する。 */
interface RowResult {
  issue?: NamePatternIssue;
  identityKey?: string;
  rendered?: string;
}

/**
 * name-pattern を全行について検証し、プレビュー警告のリストを返す。
 *
 * 検証順は CLI の `_render_and_sandbox` と同じ優先度 (escape → source 上書き →
 * Windows 不正名)。各行につき最初に失敗したクラスのみ報告する。collision のみ
 * 行間で判定する (per-row 検証を通過した行の identity を突合)。
 * 出力順は `escape → overwriteSource → invalidWindowsName → collision` で安定させる。
 *
 * 空の outputDir や 0 行では警告なし (検証不能 / 検証不要)。
 */
export function computeNamePatternIssues(opts: {
  pattern: string;
  outputDir: string;
  sourceVideo: string | null;
  rows: SandboxRow[];
}): NamePatternIssue[] {
  const { pattern, outputDir, sourceVideo, rows } = opts;
  const issues: NamePatternIssue[] = [];
  if (!outputDir || rows.length === 0) return issues;

  const root = { ...parseWinPath(outputDir), parts: collapse(parseWinPath(outputDir).parts) };
  const source = sourceVideo
    ? { ...parseWinPath(sourceVideo), parts: collapse(parseWinPath(sourceVideo).parts) }
    : null;

  const results: RowResult[] = rows.map((row) => {
    const rendered = formatMatchFilename(pattern, row.index, row.type, row.startSec);
    const candidate = winJoin(root, rendered);
    // 1. containment (CLI: resolved == root または外 → escape)
    if (!isStrictlyInside(root, candidate)) {
      return {
        issue: {
          kind: 'escape',
          sampleName: rendered,
          message: `"${rendered}" は出力先フォルダの外に解決されます。書き出し時に拒否されます ('..' / 絶対パス / ドライブ相対を除いてください。{type} は metadata の値をそのまま使うため注意)`,
        },
      };
    }
    // 2. source video 上書き (CLI: resolved == source、大小文字無視)
    if (source && samePathCaseInsensitive(candidate, source)) {
      return {
        issue: {
          kind: 'overwriteSource',
          sampleName: rendered,
          message: `"${rendered}" は元動画 (source) と同じファイルを指します。書き出し時に拒否されます (出力先か名前を変えてください)`,
        },
      };
    }
    // 3. Windows 不正名 (CLI: `:` は resolved component 内で禁止 / 予約デバイス名)
    for (const part of candidate.parts) {
      if (part.includes(':')) {
        return {
          issue: {
            kind: 'invalidWindowsName',
            sampleName: rendered,
            message: `"${rendered}" は Windows で使えない名前です — ':' はファイル名に使えません (NTFS 代替データストリーム扱いになります)。書き出し時に拒否されます`,
          },
        };
      }
      const bare = part.replace(/[. ]+$/, '').toLowerCase();
      if (bare && WIN32_RESERVED_NAMES.has(bare)) {
        return {
          issue: {
            kind: 'invalidWindowsName',
            sampleName: rendered,
            message: `"${rendered}" は Windows の予約デバイス名 (${part} = NUL / CON / PRN / AUX / COM1-9 / LPT1-9) を含みます。書き出し時に拒否されます`,
          },
        };
      }
    }
    // 4. collision 用の identity を控える (fold は CLI `_identity_key` と同寸)
    return { identityKey: identityKey(candidate), rendered };
  });

  // per-row 検証を通過した行の identity 突合 (collision)
  const identityToRendered = new Map<string, string>();
  for (const r of results) {
    if (r.issue || r.identityKey === undefined || r.rendered === undefined) continue;
    const prev = identityToRendered.get(r.identityKey);
    if (prev !== undefined) {
      r.issue = {
        kind: 'collision',
        sampleName: r.rendered,
        message: `複数の試合が同じファイル "${r.rendered}" (="${prev}") に解決されます。{idx} か {idx:03} を名前に入れてください`,
      };
    } else {
      identityToRendered.set(r.identityKey, r.rendered);
    }
  }

  const order: NamePatternIssueKind[] = [
    'escape',
    'overwriteSource',
    'invalidWindowsName',
    'collision',
  ];
  const seen = new Set<string>();
  for (const kind of order) {
    for (const r of results) {
      if (!r.issue || r.issue.kind !== kind) continue;
      const dedupeKey = `${kind}:${r.issue.sampleName}`;
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);
      issues.push(r.issue);
    }
  }
  return issues;
}
