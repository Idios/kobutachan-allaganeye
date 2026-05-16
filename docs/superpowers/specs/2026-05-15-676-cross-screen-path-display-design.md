# #676 — GUI 5 画面横断 file path 表示統一 (design)

> **Status**: Design 確定 (ユーザー approval 2026-05-15)
> **作成**: 2026-05-15 / session `pedantic-rubin-7b9b0c` / Lane III (Group E、Wave 1 後段)
> **元 issue**: [#676](https://github.com/Idios/kobutachan-allaganeye/issues/676) (P3-low, bug, l2a-gui)
> **Gating**: Lane V Phase 2 ([#694](https://github.com/Idios/kobutachan-allaganeye/issues/694)) merged via [PR #745](https://github.com/Idios/kobutachan-allaganeye/pull/745) (commit 7b65bf4) — 5 screen 編集の base 安定済
> **Roadmap**: [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md](../plans/2026-05-13-l2-v020-roadmap-update.md) §Group E

## 1. Goals / Non-goals

### Goals (issue #676 受け入れ条件)

ユーザーが「いま GUI で扱っている動画はどのフォルダのどのファイルか」を 5 画面のすべての主要表示領域で識別できるようにする。同名ファイルが別フォルダにあるケースを基本想定。

1. Drop SelectedCard / Detecting (running + error) / Complete topBar / Preview header / Export header の 7 箇所すべてで絶対 path が可視
2. 表示形式を全画面で統一: **ファイル名主表示 (primary) + 親ディレクトリ副表示 (secondary、左側省略 truncate)** — 直近の録画リスト ([PR #655](https://github.com/Idios/kobutachan-allaganeye/pull/655) Round 2) の精神を 2 段構造に発展させた版
3. 横断 UI ルールを doc 化して再発を防ぐ (`docs/ui-interaction-spec.md §1.6` 新設)
4. 各画面に render テストを追加 (vitest)、integration smoke 1 ケースで遷移後の継続表示を担保

### Non-goals (scope-guard で弾く)

- 既存 recent list (§2.1.3) の見た目変更 — PR #655 で確定済、本 §1.6 では「行リスト密度確保のための例外」として明文化
- `aria-label` 修正 — `a11y-policy.md` 準拠で新規追加なし、既存 (`直近の録画 ${fileName}`) も変更なし
- path 表示の i18n / 短縮表示の長さ調整スライダ / breadcrumb 形式 (`> 区切り`) 等の UX 拡張
- `info.fileName` (Rust 由来) の廃止 — VideoProbeInfo の型 surface は不変、SelectedCard 内のみ `splitPath(info.path).fileName` に差し替え
- SideRail 系の見た目調整 (#677 は別 lane で削除済、commit acf7c49)

## 2. 決定事項サマリ (brainstorming で確定)

| 項目 | 決定 | 根拠 |
| --- | --- | --- |
| 表示フォーマット | **B 案**: fileName 主役 (primary) + 親フォルダ副表示 (secondary、dim・左側省略) | 2026-05-15 visual companion で 3 案 (フルパス1行 / fileName主+親dir副 / 2行表示) から選択。同名ファイル判別目的に最も読みやすく、縦スペース消費も 2 行で過剰でない |
| a11y / aria-label | **新規追加なし**、`title` 属性のみ | `a11y-policy.md` 「screen reader 専用属性は新規追加しない」方針に完全準拠。FF14 PvP プレイヤー想定で screen reader ユースケースなし。`title` は a11y-policy が推奨 |
| CSS 共通化先 | **新規 `gui/src/styles/path-display.module.css`** (CSS Module) | プロジェクトの CSS Modules パターンに沿う。`tokens.css` の責務 (token + base reset) を侵さない。drift 防止のため画面別コピペは不採用 |
| UI ルール doc 配置 | **`docs/ui-interaction-spec.md §1.6`** 新設 | doc 責務 (UI 部品横断原則) に最も合致。a11y-policy.md からは 1 行クロスリファレンスのみ |
| Complete の path source | **`videoSource`** (`selectedVideoPath ?? metadata.source`) に統一 | Preview/Export と同じ source-of-truth に揃え画面間 source drift を解消。issue の AC 「`metadata.source` 表示に `title` 追加」表記は実装方針表 (source of truth) に従って読み替え |
| 実装順 | **A**: ボトムアップ (基盤 → 画面別 TDD → 横断検証) | 各 chapter = 独立 commit + 独立 review unit、subagent-driven-development の per-task 切り出しに最適 |

## 3. Architecture & shared building blocks

### 3.1 変更ファイル一覧

| 区分 | ファイル | 操作 |
| --- | --- | --- |
| 共有 util | [`gui/src/utils/path.ts`](../../../gui/src/utils/path.ts) | `splitPath(absPath)` 関数を追加 (既存 `stripExtendedPathPrefix` / `joinPath` の隣) |
| 共有 util test | [`gui/src/utils/path.test.ts`](../../../gui/src/utils/path.test.ts) | `splitPath` の単体テスト追加 |
| 共有 CSS | `gui/src/styles/path-display.module.css` | **新規** |
| Drop SelectedCard | [`gui/src/screens/DropScreen.tsx`](../../../gui/src/screens/DropScreen.tsx) 476-502 | `.selectedName` 単行 → primary+secondary 構造 |
| Detecting running header | [`gui/src/screens/DetectingScreen.tsx`](../../../gui/src/screens/DetectingScreen.tsx) 564-581 | `displayFile` basename 抽出を廃止 → `splitPath(selectedVideoPath)` → primary+secondary |
| Detecting error view | [`gui/src/screens/DetectingScreen.tsx`](../../../gui/src/screens/DetectingScreen.tsx) 289 / 762 | `displayFile` prop の型を `{fileName, parentDir, full}` に拡張 |
| Complete topBar | [`gui/src/screens/CompleteScreen.tsx`](../../../gui/src/screens/CompleteScreen.tsx) 99-102, CompleteScreen.module.css | `metadata.source` 単行 → `videoSource` 由来の primary+secondary |
| Preview header (新規領域) | [`gui/src/screens/PreviewScreen.tsx`](../../../gui/src/screens/PreviewScreen.tsx) 621-650, PreviewScreen.module.css | `.headerInfo` 内、`.caption` の上に path display を追加 + `.headerFileName` クラス |
| Export header (新規領域) | [`gui/src/screens/ExportScreen.tsx`](../../../gui/src/screens/ExportScreen.tsx) 527-532, ExportScreen.module.css | header 左 div 内、caption の上に path display を追加 + `.headerFileName` クラス |
| 各 screen test | DropScreen / DetectingScreen / CompleteScreen / PreviewScreen / ExportScreen `*.test.tsx` | render テスト追加 (fileName / parentDir / title / data-testid) |
| Integration smoke | [`gui/src/__tests__/flow.integration.test.tsx`](../../../gui/src/__tests__/flow.integration.test.tsx) | drop → detect → complete → preview → export で path が継続表示される smoke 1 ケース |
| 横断 doc | [`docs/ui-interaction-spec.md`](../../ui-interaction-spec.md) | §1.6 「ファイルパス表示の原則」を新設、§2.1.4 / §2.2.2 / §2.2.8 (新規、Detecting error view) / §2.3.2 / §2.4.16 (新規、Preview header path display) / §2.5.2 に「§1.6 準拠」追記 ※§2.4 / §2.5 の既存サブセクション anchor を壊さないため新規セクションは末尾追加 (§2.4.15 emptyNote / §2.5.16 emptyNote の後) |
| a11y doc クロスリファレンス | [`docs/a11y-policy.md`](../../a11y-policy.md) | 「`title` 属性は ui-interaction-spec.md §1.6 参照」1 行追加 (新規節は作らない) |

### 3.2 path source-of-truth (全画面統一)

| 画面 | source |
| --- | --- |
| Drop SelectedCard | `info.path` (`VideoProbeInfo`) |
| Detecting running header | `selectedVideoPath` (`appStateStore`) |
| Detecting error view | `selectedVideoPath` |
| Complete topBar | `videoSource` = `selectedVideoPath ?? metadata.source` |
| Preview header | `videoSource` (PreviewScreen.tsx:261 既存定義) |
| Export header | `videoSource` (ExportScreen.tsx:126 既存定義) |

どの画面でも「絶対 path 1 個」を `splitPath()` に渡せば `{fileName, parentDir}` が得られる構造。

### 3.3 `splitPath()` ユーティリティ

`gui/src/utils/path.ts` に追加 (既存 helper の隣):

```ts
/**
 * 絶対 path を fileName (basename) と parentDir に分解する。
 * Windows `\\?\` 拡張長 prefix は内部で stripExtendedPathPrefix() を通す。
 * セパレータ末尾 / セパレータなし / parentDir 空 (= drive root) の edge case
 * もすべて空文字列にフォールバックする (例外を投げない、UI 表示用)。
 *
 * 例:
 *  - "E:\\videos\\foo.mkv"  → { fileName: "foo.mkv",  parentDir: "E:\\videos" }
 *  - "/tmp/foo.mp4"         → { fileName: "foo.mp4",  parentDir: "/tmp" }
 *  - "\\\\?\\C:\\foo.mkv"   → { fileName: "foo.mkv",  parentDir: "C:\\" }
 *  - "foo.mkv"              → { fileName: "foo.mkv",  parentDir: "" }
 *  - ""                     → { fileName: "",         parentDir: "" }
 */
export function splitPath(absPath: string): { fileName: string; parentDir: string };
```

- 既存 `deriveDefaultOutDir` ([ExportScreen.tsx:1034](../../../gui/src/screens/ExportScreen.tsx#L1034)) と同じ「`lastIndexOf('/' or '\\')`」ロジックを汎用化
- normalize は **stripExtendedPathPrefix のみ**。OS-native separator 変換はしない (元 path の見た目を保つ)
- `VideoProbeInfo.fileName` (Rust 由来) と `splitPath(info.path).fileName` は常に一致する想定 (Rust 側 `Path::file_name()` 等価)

### 3.4 共有 CSS module `path-display.module.css`

```css
/*
 * gui/src/styles/path-display.module.css
 *
 * #676 — 5 画面 (drop / detecting / complete / preview / export) で共通の
 * 「ファイル名 + 親ディレクトリ」2 段表示。primary 側のフォントサイズは
 * 画面側 (e.g. DropScreen.module.css `.selectedName`) で指定し、本 module
 * は色味と truncate 規約のみ提供する。
 *
 * ui-interaction-spec.md §1.6 「ファイルパス表示の原則」も参照。
 */

.pathDisplay {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0; /* flex 子のとき overflow を効かせるため */
}

.pathSecondary {
  font-family: var(--ae-font-mono);
  font-size: 11px;
  color: var(--ae-text-dim);
  /* left-side truncation (PR #655 .recentName と同設計):
     direction:rtl で ellipsis 位置を左に / unicode-bidi:plaintext で
     文字自体は LTR 描画を維持 */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  direction: rtl;
  text-align: left;
  unicode-bidi: plaintext;
  min-width: 0;
}
```

- **`.pathDisplay`** = container (flex col + min-width:0)。`title={fullPath}` をここに付けて hover 範囲を 2 行ぶん確保
- **`.pathSecondary`** = 親 dir 行。font-size / 色は共通固定 (11px dim mono)。truncate は recent list の `.recentName` と完全同一規則
- primary (fileName) のクラスは**画面側 CSS が provide** (`.selectedName` / `.fileName` / `.errorFile` / `.sourceName` / 新 `.headerFileName`)。primary を共通化しないのは、各画面の既存タイポグラフィ階層を壊さないため

### 3.5 共通 JSX 構造

すべての画面で:

```tsx
<div className={pathStyles.pathDisplay} title={fullPath} data-testid="<screen>-path">
  <div className={styles.<screenSpecificPrimaryClass>}>{fileName || '(video)'}</div>
  {parentDir && <div className={pathStyles.pathSecondary}>{parentDir}</div>}
</div>
```

- `title` は container に 1 個。hover で full path 表示
- `parentDir` が空文字列のとき (path セパレータなし、drive root) は secondary 行を非表示 → fileName 単独表示にフォールバック
- `fileName` が空 (`splitPath('')` の戻り値) のときの placeholder `'(video)'` は Detecting の既存挙動を踏襲

## 4. 画面別変更詳細

### 4.1 Drop SelectedCard ([DropScreen.tsx:476-502](../../../gui/src/screens/DropScreen.tsx#L476))

```diff
-<div className={styles.selectedName}>{info.fileName}</div>
+{(() => {
+  const { fileName, parentDir } = splitPath(info.path);
+  return (
+    <div className={pathStyles.pathDisplay} title={info.path} data-testid="drop-selected-path">
+      <div className={styles.selectedName}>{fileName || '(video)'}</div>
+      {parentDir && <div className={pathStyles.pathSecondary}>{parentDir}</div>}
+    </div>
+  );
+})()}
```

- `info.fileName` (Rust 由来) は `splitPath(info.path).fileName` で代替
- `.selectedName` CSS は既存 (16px / `--ae-text-bright`) のまま primary 利用

### 4.2 / 4.3 DetectingScreen — running header + error view

親 component で `displayFile` を文字列 1 個から `{ fileName, parentDir, full }` 形に変更:

```diff
-const displayFile = selectedVideoPath?.split(/[/\\]/).pop() ?? '(video)';
+const displayPath = selectedVideoPath
+  ? { ...splitPath(selectedVideoPath), full: selectedVideoPath }
+  : { fileName: '(video)', parentDir: '', full: '' };
```

`DetectingScreen.tsx:577` (running header `.fileName`):

```diff
-<div className={styles.fileName}>{displayFile}</div>
+<div className={pathStyles.pathDisplay} title={displayPath.full} data-testid="detecting-path">
+  <div className={styles.fileName}>{displayPath.fileName}</div>
+  {displayPath.parentDir && <div className={pathStyles.pathSecondary}>{displayPath.parentDir}</div>}
+</div>
```

`DetectingScreen.tsx:762` (error view `.errorFile`): 同形に置き換え、`data-testid="detecting-error-path"`。`.fileName` (14px) と `.errorFile` (13px) の CSS は既存のまま primary として再利用。`DetectingErrorView` の `displayFile: string` prop 型を `displayPath: { fileName: string; parentDir: string; full: string }` に拡張。

### 4.4 CompleteScreen topBar ([CompleteScreen.tsx:99-102](../../../gui/src/screens/CompleteScreen.tsx#L99))

```diff
 <div className={styles.sourceBox}>
   <div className={styles.sourceCaption}>観測完了</div>
-  <div className={styles.sourceName}>{metadata.source}</div>
+  {(() => {
+    const src = selectedVideoPath ?? metadata.source;  // = videoSource
+    const { fileName, parentDir } = splitPath(src);
+    return (
+      <div className={pathStyles.pathDisplay} title={src} data-testid="complete-path">
+        <div className={styles.sourceName}>{fileName || '(video)'}</div>
+        {parentDir && <div className={pathStyles.pathSecondary}>{parentDir}</div>}
+      </div>
+    );
+  })()}
 </div>
```

- `selectedVideoPath` を `useAppStateStore` から購読 (既に `thumbVideoPath` 計算で line 54 で取得済み — 再利用)
- 既存 `.sourceName` (13px / text-bright / margin-top: 2px) は primary として残置
- 受け入れ条件の「`.sourceName` CSS に truncate ルールを明示」は本構造で `.pathSecondary` 側 (secondary 行) に集約される形で吸収。`.sourceName` 自体は plain text のままで OK

### 4.5 PreviewScreen header (新規領域、[PreviewScreen.tsx:621-650](../../../gui/src/screens/PreviewScreen.tsx#L621))

`.headerInfo` 内、`.caption` の **上**に挿入:

```diff
 <div className={styles.headerInfo}>
+  {videoSource && (() => {
+    const { fileName, parentDir } = splitPath(videoSource);
+    return (
+      <div className={pathStyles.pathDisplay} title={videoSource} data-testid="preview-path">
+        <div className={styles.headerFileName}>{fileName || '(video)'}</div>
+        {parentDir && <div className={pathStyles.pathSecondary}>{parentDir}</div>}
+      </div>
+    );
+  })()}
   <div className={styles.caption}>境界調整 ⸱ BOUNDARY CALIBRATION</div>
   <div className={styles.nameRow}>...</div>
 </div>
```

PreviewScreen.module.css に新 class:

```css
.headerFileName {
  font-family: var(--ae-font-body);
  font-size: 13px;
  color: var(--ae-text-bright);
  margin-bottom: 4px;
}
```

### 4.6 ExportScreen header (新規領域、[ExportScreen.tsx:527-532](../../../gui/src/screens/ExportScreen.tsx#L527))

caption/title の左 div 内、caption の **上**に挿入:

```diff
 <div>
+  {videoSource && (() => {
+    const { fileName, parentDir } = splitPath(videoSource);
+    return (
+      <div className={pathStyles.pathDisplay} title={videoSource} data-testid="export-path">
+        <div className={styles.headerFileName}>{fileName || '(video)'}</div>
+        {parentDir && <div className={pathStyles.pathSecondary}>{parentDir}</div>}
+      </div>
+    );
+  })()}
   <div className={styles.caption}>エクスポート</div>
   <div className={styles.title}>{countedMatches.length} 試合を書き出す</div>
 </div>
```

ExportScreen.module.css にも `.headerFileName` を追加 (Preview と 1:1 同等):

```css
.headerFileName {
  font-family: var(--ae-font-body);
  font-size: 13px;
  color: var(--ae-text-bright);
  margin-bottom: 4px;
}
```

## 5. doc §1.6 「ファイルパス表示の原則」新設

[`docs/ui-interaction-spec.md`](../../ui-interaction-spec.md) §1.5 (エラー表示の一貫性) の **直後**に新設。

```markdown
### 1.6 ファイルパス表示の原則 (#676)

**原則**: ユーザーが現在扱っている動画ファイルを「どのフォルダのどのファイルか」識別できるよう、
5 画面 (drop / detecting / complete / preview / export) のすべての主要表示領域で
**絶対 path** を可視化する。fileName だけの表示は禁止 (同名ファイル区別不能のため)。

| 観点 | 規定 |
|---|---|
| 表示形式 | **fileName 主表示 (primary) + 親ディレクトリ副表示 (secondary)** の 2 段構造 |
| primary 行 | fileName のみ。font-size は各画面のタイポグラフィ階層に従う (13-16px、`--ae-text-bright`) |
| secondary 行 | parent dir のみ。`gui/src/styles/path-display.module.css` の `.pathSecondary` クラスを使用 (11px / `--ae-text-dim` / `--ae-font-mono`) |
| truncate | secondary 行は左側省略 (RTL ellipsis + `unicode-bidi:plaintext`)。`.pathSecondary` に集約 |
| hover ツールチップ | 必ず container `<div>` に `title={fullPath}` を付与。primary/secondary 個別ではなく container 1 個 |
| path source-of-truth | drop=`info.path` / detecting=`selectedVideoPath` / complete・preview・export=`videoSource` (= `selectedVideoPath ?? metadata.source`) |
| path 分解 | `gui/src/utils/path.ts` の `splitPath(absPath)` で `{fileName, parentDir}` を取得 (例外不投げ) |
| parentDir 空 | drive root などで parentDir が空文字列のとき、secondary 行は非表示 (primary 単独) |
| data-testid | container に `<screen>-path` を基本とする。1 画面に複数 path 表示があるとき or phase 固有のとき context 接尾辞を入れる (例: `drop-selected-path` は `phase=selected` 限定 / `detecting-path` (running) と `detecting-error-path` (error view) で区別) |
| a11y | `aria-label` 等の screen reader 専用属性は新規追加しない (a11y-policy.md 準拠)。`title` 属性 + visible text のみで識別性を担保 |
| recent list (§2.1.3) | **例外**: 行 layout 上 1 行 (フルパス + 左側省略) を維持。PR #655 で確立した `.recentName` をそのまま使用。本 §1.6 の 2 段構造は適用しない |

**アンチパターン**:

- fileName のみで親 dir を表示しない (#676 報告の SelectedCard / Detecting の旧実装が該当)
- `metadata.source` を直に文字列バインドし truncate / title を付けない (#676 報告の CompleteScreen 旧実装が該当)
- 画面ごとに truncate ルールを CSS にコピペ (drift の温床、共通 module で集約)

**参考実装**: 直近の録画リスト ([DropScreen.tsx:421-426](../gui/src/screens/DropScreen.tsx#L421), PR #655 Round 2) —
1 行版だが「直近 path 識別」の同種要求への先行解。本 §1.6 は SelectedCard を含む他全画面用の 2 段版。

**画面別適用箇所**: §2.1.4 (Drop SelectedCard) / §2.2.2 (Detecting Header) / §2.2.8 (Detecting error view、新規) /
§2.3.2 (Complete sourceBox) / §2.4.16 (Preview header path display、新規) / §2.5.2 (Export header) — 各節に「§1.6 準拠」リンク。
新規サブセクション (§2.2.8 / §2.4.16) は既存 anchor 互換のため各 §2 の末尾に追加する。
```

各 §2.X 部品節への 1 行追加例 (§2.3.2):

```diff
-| 例外 / edge case | full path が長すぎる場合の overflow / ellipsis は CSS 任せ。a11y は plain text、screen reader はそのまま読み上げる。Phase 2.5 で basename + tooltip full path に変更する選択肢あり (#587) |
+| 例外 / edge case | **§1.6 ファイルパス表示の原則** に準拠。`videoSource` を `splitPath()` で分解、primary `.sourceName` (fileName) + secondary `.pathSecondary` (parentDir 左側省略) + container `title={videoSource}` の 2 段構造 (#676)。screen reader は plain text 読み上げ、`aria-label` は新規追加しない |
```

[`docs/a11y-policy.md`](../../a11y-policy.md) `## disabled 理由表示` の直下に 1 行クロスリファレンス追加:

```markdown
## ファイルパス表示の `title` 属性

5 画面の path 表示は **[ui-interaction-spec.md §1.6](ui-interaction-spec.md)** が source of truth。
`title` 属性 (hover tooltip) で full path を出し、`aria-label` は新規追加しない方針。
```

## 6. テスト

### 6.1 単体テスト: `splitPath`

[`gui/src/utils/path.test.ts`](../../../gui/src/utils/path.test.ts) に追加:

```ts
describe('splitPath', () => {
  it('splits a Windows path', () => {
    expect(splitPath('E:\\videos\\foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: 'E:\\videos' });
  });
  it('splits a POSIX path', () => {
    expect(splitPath('/tmp/foo.mp4'))
      .toEqual({ fileName: 'foo.mp4', parentDir: '/tmp' });
  });
  it('strips \\\\?\\ prefix before splitting', () => {
    expect(splitPath('\\\\?\\C:\\videos\\foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: 'C:\\videos' });
  });
  it('returns empty parentDir for separator-less path', () => {
    expect(splitPath('foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: '' });
  });
  it('returns both empty for empty string', () => {
    expect(splitPath('')).toEqual({ fileName: '', parentDir: '' });
  });
  it('handles drive-root file', () => {
    expect(splitPath('C:\\foo.mkv'))
      .toEqual({ fileName: 'foo.mkv', parentDir: 'C:' });
  });
});
```

### 6.2 画面別 render test

各 `*.test.tsx` に追加 (5 画面 × 1-2 ケース):

```ts
// DropScreen.test.tsx 例 (SelectedCard render 後)
it('shows full path with fileName primary and parentDir secondary (#676)', async () => {
  await selectVideo({ path: 'E:\\videos\\20260116\\foo.mkv', fileName: 'foo.mkv', ... });
  const container = screen.getByTestId('drop-selected-path');
  expect(container).toHaveAttribute('title', 'E:\\videos\\20260116\\foo.mkv');
  expect(within(container).getByText('foo.mkv')).toBeInTheDocument();
  expect(within(container).getByText('E:\\videos\\20260116')).toBeInTheDocument();
});
```

同パターンで `detecting-path` / `detecting-error-path` / `complete-path` / `preview-path` / `export-path` を assert。

### 6.3 Integration smoke

[`gui/src/__tests__/flow.integration.test.tsx`](../../../gui/src/__tests__/flow.integration.test.tsx) に 1 ケース追加:

```ts
it('keeps the full path visible across drop → detect → complete → preview → export (#676)', async () => {
  // drop でフルパス確定
  // → detect で getByTestId('detecting-path') が同 path を保持
  // → complete で getByTestId('complete-path') が同 path
  // → preview で getByTestId('preview-path') が同 path
  // → export で getByTestId('export-path') が同 path
});
```

### 6.4 jest-axe

各 screen の既存 axe テスト (`expect(await axe(container)).toHaveNoViolations()`) を再走させ違反ゼロ確認。
plain text + `title` は a11y 違反対象外なので追加違反は出ない想定。

## 7. リスクと既知 edge case

| リスク | 影響 | 対処 |
| --- | --- | --- |
| `videoSource` が null (sample mode 直後の Preview / Export 着地以前) | path display 領域が消える (条件付き render) | `videoSource && (...)` でガード。sample mode banner が別途出るので機能影響なし |
| parentDir 空文字列 (drive root `C:\foo.mkv`) | secondary 行非表示で fileName のみ表示 | 仕様内 (§1.6「parentDir 空 → 非表示」) |
| `\\?\` extended-length prefix が path にそのまま残る | `direction:rtl` で left-side ellipsis が awkward に切れる | `splitPath` 内で `stripExtendedPathPrefix` を通すので入力時点で除去 |
| Preview/Export 新規領域追加で header 縦寸法が +2 行ぶん増加 | レイアウト崩れ (screen の min-height で overflow) | 13px + 11px ≒ 28px 増。各 screen の既存 padding/gap で吸収可能 (Preview `.screen` は overflow:auto、Export `.screen` は flex)。実機検証で要確認 |
| Detecting `displayFile` の prop 型変更 (`string` → object) | `DetectingErrorView` の既存 jsdoc / 型を更新する必要 | TDD で型 first に書く |
| 既存 recent list との見た目差 | 1 行版 vs 2 段版で表記が異なる | §1.6 で「recent list は例外」として明文化 (UI 統一性は損なわれるが、行リストの密度確保のための既存例外として doc 化) |

## 8. 受け入れ条件 (issue #676 とのマッピング)

`/enforce-acceptance-criteria` skill で逐条検証する形で issue AC と本 spec を 1:1 対応させる:

| issue #676 AC | 本 spec の対応箇所 | 実装後の verify 観点 |
| --- | --- | --- |
| Drop SelectedCard: `info.path` を表示 | §4.1 | `getByTestId('drop-selected-path')` の `title` 属性が `info.path` と一致、fileName + parentDir が render |
| Detecting header (running view): `selectedVideoPath` を表示 | §4.2 | `getByTestId('detecting-path')` の `title` 属性が `selectedVideoPath` と一致 |
| Detecting error view: 同上 | §4.3 | `getByTestId('detecting-error-path')` で同 assertion |
| Complete topBar: `title={metadata.source}` 追加 + `.sourceName` truncate | §4.4 | `getByTestId('complete-path')` の `title` 属性が `videoSource` (= `selectedVideoPath ?? metadata.source`) と一致。truncate は `.pathSecondary` 側に集約 (AC 表記「metadata.source」は brainstorming で `videoSource` に読み替え確定) |
| Preview header: `videoSource` 表示領域を新設 | §4.5 | `getByTestId('preview-path')` が存在し `title` 属性が `videoSource` と一致 |
| Export header: `videoSource` 表示領域を新設 | §4.6 | `getByTestId('export-path')` が存在し `title` 属性が `videoSource` と一致 |
| UI ルール doc: `docs/ui-interaction-spec.md` 新節 (or a11y-policy.md) に明記 | §5 | `docs/ui-interaction-spec.md §1.6` 存在 + 各 §2.X 部品節からの参照リンク + `docs/a11y-policy.md` クロスリファレンス 1 行 |
| テスト: 各画面 render テスト追加 (vitest) | §6.1-6.3 | `npm test` で `splitPath` 6 ケース + 各画面 1-2 ケース + integration smoke 1 ケースが pass |

## 9. 実機検証 trigger 判定 (Iron Law 6)

本 PR は **GUI TS / CSS / vitest / 型変更** のみで Tauri 命令 / GPU / audio / ffmpeg / 長時間動画には触れない。

→ **`cd gui && npm run lint && npm run typecheck && npm test && npm run build`** + `cd gui/src-tauri && cargo check` の全 pass で machine-verified。
→ **実機 Tauri 起動の検証は Iron Law 6 必須 trigger 対象外** (mock テストで担保できる範疇)。

ただし「Preview/Export の header に新規領域追加で縦寸法 +28px」は単純なレイアウト変更なので、PR 段階で **実機 Tauri での目視を `AskUserQuestion` で任意 (recommended) 依頼**する (Iron Law 6 必須ではない、好意での確認)。

## 10. 関連 / 参考

- [issue #676](https://github.com/Idios/kobutachan-allaganeye/issues/676) — 元 issue (P3-low bug)
- [PR #655](https://github.com/Idios/kobutachan-allaganeye/pull/655) Round 2 — recent list 1 行版 (本 spec の参考実装)
- [PR #745](https://github.com/Idios/kobutachan-allaganeye/pull/745) (#694) — Lane V Phase 2 unified ErrorState merge (Lane III gating 解除)
- [docs/ui-interaction-spec.md](../../ui-interaction-spec.md) — UI 部品レベル仕様 (§1.6 新設先)
- [docs/a11y-policy.md](../../a11y-policy.md) — a11y 方針 (`aria-label` 新規追加なしの根拠)
- [docs/superpowers/plans/2026-05-13-l2-v020-roadmap-update.md](../plans/2026-05-13-l2-v020-roadmap-update.md) — Lane III / Group E roadmap
- [gui/src/utils/path.ts](../../../gui/src/utils/path.ts) — `splitPath` 追加先 (既存 `stripExtendedPathPrefix` / `joinPath` の隣)
- [gui/src/screens/DropScreen.module.css](../../../gui/src/screens/DropScreen.module.css) `.recentName` (162-171) — `.pathSecondary` のルール出自
