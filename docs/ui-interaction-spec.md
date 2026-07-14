# Allagan Eye GUI — UI Interaction Spec

> **スコープ**: 5 画面 (drop / detecting / complete / preview / export) の **UI 部品ごとの操作 → 状態遷移 / store mutation / 例外処理**を明文化する source of truth。画面間遷移は [ui-architecture.md](ui-architecture.md)、画面レイアウトとデザインシステムは [design/README.md](design/README.md)、metadata.json データ契約は [metadata-spec.md](metadata-spec.md) を参照。
>
> **a11y 方針**: focus visible / キーボード全機能操作 / disabled 理由表示 / screen reader scope 等の cross-cutting 方針は [a11y-policy.md](a11y-policy.md) を参照 (#587)。本 doc は UI 部品レベルの仕様、a11y-policy.md は application-wide 方針を担当。

本 doc は [#590](https://github.com/Idios/kobutachan-allaganeye/issues/590) で起票し、[#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) (PreviewScreen の state mutation flow / disabled 理由表示 / silent edit loss) の root cause を構造的に再発防止することが第一目的。

## 1. 共通原則

5 画面すべての UI 部品は本節の原則に準拠する。違反は #589 系統のバグとして扱い、レビュー時は本節を逐条照合する。

### 1.1 state mutation flow: input → store → dirty 即時反映

**原則**: フォーム input (text / number / select / textarea / radio / checkbox) は onChange で `metadataStore` の `updateMatch` (もしくは同等 mutation) を **debounce 200ms 経由**で呼び、store の `dirty` フラグを即時に立てる。

| 観点 | 規定 |
| --- | --- |
| debounce 値 | 200ms (連続入力中の中間値で reducer / re-render が発火しすぎない最小値) |
| auto-save (#517) との関係 | 独立。auto-save 側は別 debounce 500ms で `metadata.draft.json` に書く。UI dirty 反映 (200ms) と disk persist (500ms) を分離 |
| 即時 commit が必要な操作 | toggle (skip / type 切替) / 数値 stepper クリック / プルダウン選択 — debounce せず onChange で同期 commit |
| 例外 (commit しない) | UI 一時表示専用 (フィルタ・検索・ソート選択等)。store に commit しない明示が必要な場合のみ local state でよい |

**アンチパターン**: local state (`useState`) のみで保持し apply ボタン押下時に `updateMatch` を一括コールする設計。dirty バッジ・auto-save・confirm がすべて不発になる。`PreviewScreen` の #589 修正前がこのパターンに該当し、debounce 200ms 経由の `updateMatch` + flush-on-navigate に作り変えて解消した (現状は §2.4.2 / §2.4.6 / §2.4.7 が source of truth)。

**Tip**: フォーカス維持や IME 確定途中に store re-render で input が破壊されるのを避けるため、display 用 controlled value は local state で持ち、onChange で local state を更新しつつ debounce で store に commit する 2 レイヤ実装でよい (local state を捨てるのではなく、commit 経路に乗せる)。

### 1.2 disabled 条件は理由表示必須 (tooltip + inline)

**原則**: ボタン・input の `disabled=true` は必ず理由を表示する。表示は **(a) 当該要素の tooltip (`title` 属性 + `aria-describedby`)** と **(b) 近傍の inline hint (small text)** の両方を提供する。

| 表示形式 | 用途 | 必須範囲 |
| --- | --- | --- |
| tooltip 単独 | 副次ボタン (FrameStrip 内 stepper、行内アイコンボタン等) | 副次 UI |
| inline hint 単独 | 主要 CTA 周辺で常時可視化したい理由 | 主要 CTA は inline 必須 |
| tooltip + inline 併用 | 主要 CTA (適用 / 元に戻す / 書き出し開始 等) | **主要 CTA は両方必須** |

- a11y 上は `aria-describedby` で理由要素の id を参照させる。screen reader が disabled の理由を読み上げる
- inline hint は赤字エラーではなく `var(--ae-text-dim)` 系の補助色。情報レベル
- 理由文は **行動指針を含む形** (例:「サンプル動画では保存できません。実際の動画を選択してください。」)。否定形だけで終わらせない

**アンチパターン**: 理由表示なしの disabled。ユーザーは原因不明で「壊れた」と認識する ([PreviewScreen.tsx:651-657](../gui/src/screens/PreviewScreen.tsx#L651) の `applying || !filePath` による sample mode 永続 disabled が #589 該当ケース。[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で tooltip / inline hint / 上部 banner を実装し解消済)。

### 1.3 silent loss 防止: dirty consume 側で confirm

**原則**: `metadataStore.dirty === true` の状態で、編集破棄を伴う操作 (画面遷移・別 match 選択・元に戻す・アプリ終了) が発火する場合、必ず confirm ダイアログを挟む。confirm は **Tauri 2 plugin-dialog の `ask`** (`@tauri-apps/plugin-dialog`) を使う — Tauri 2 の WebView2 は security の都合で `window.confirm()` / `window.alert()` / `window.prompt()` を no-op にするため native dialog 経路必須。全画面で統一すること。`tauri-plugin-dialog` 側 capability に `dialog:allow-ask` を入れること (#589 で確認)。

| consume 経路 | confirm メッセージ (canonical) | 出現画面 |
| --- | --- | --- |
| `[◀ 一覧へ]` (preview → complete) | 未保存の変更があります。破棄して一覧へ戻りますか？ | preview |
| `[書き出し]` (preview → export) | 未保存の変更があります。破棄して書き出しへ進みますか？ | preview |
| 別 match double-click / `[境界を調整]` | 未保存の変更があります。破棄して別の試合を開きますか？ | complete → preview |
| `[元に戻す]` (RestoreButton) | 編集を含めすべて元に戻します。よろしいですか？ | complete / preview |
| `[× 閉じる]` (drop screen reset) | 未保存の変更があります。破棄してファイル選択へ戻りますか？ | complete |
| 試合行 [スキップ] toggle | 不要 (toggle 自体が即時 commit + dirty 立て、破棄ではない) | complete |
| ウィンドウ × (running 中) | [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) で別途実装 (本 doc 範囲外) | 全画面 |

**確定挙動**:

- confirm OK → 編集破棄 (store の dirty 編集をクリアし `metadata` を最後の persisted 状態に戻す) + 遷移先 store 操作
- confirm キャンセル → 編集保持、画面遷移なし
- dirty=false (apply 直後 / 編集なし) → confirm スキップで即遷移

**アンチパターン**: dirty=true なのに confirm せず遷移する設計 (#589 修正前の `PreviewScreen` の handleBack / handleExport が該当、現在は §2.4.1 / §2.4.14 経由で §1.3 準拠 + canonical 文言統一済)。

**lint 強制 ([#643](https://github.com/Idios/kobutachan-allaganeye/issues/643))**: 上記 canonical 違反 (`window.confirm` / `window.alert` / `window.prompt` の bare 呼び出しおよび `window.X` 経由 member access) は `gui/eslint.config.js` の `no-restricted-globals` + `no-restricted-properties` で **error として block** する。`npm run lint` / CI gui-frontend job が fail し、IDE 上でも即時警告される。エラーメッセージに plugin-dialog 代替 API へのリンクを含める。

### 1.4 sample mode (filePath==null) の read-only 明示

**原則**: `metadataStore.loadSample()` で読み込まれた sample metadata (`metadataStore.filePath === null`) は **編集不可 (read-only)** として扱い、編集系 UI 部品はすべて grayed out + 上部に常時 hint を表示する。

| 部品種別 | sample mode の扱い |
| --- | --- |
| 編集 input (start/end TC、name、type/type_override、skip toggle 等) | **disabled** (tooltip 理由表示) |
| 主要 CTA (適用、元に戻す) | **disabled** + inline hint「サンプル動画では保存できません」 |
| 編集を伴わないナビゲーション (画面遷移、行選択、stepper の表示更新等) | **操作可** (学習目的を阻害しない) |
| 開発者向け StateSwitcher (右上 float) | sample mode と独立に常時操作可 |
| 上部 inline banner | 常時表示「サンプル動画です。実際の動画を選択すると保存できます。」 |

検出条件は **`metadataStore.filePath === null`** に集約。`metadata !== null && filePath === null` を「sample である」の唯一の判定として使い、コンポーネント個別に `loadSample` 経由かを推定する分岐を作らない。

### 1.5 エラー表示の一貫性 (inline + toast)

**原則**: 失敗系の表示は **(a) 失敗を引き起こした操作元の inline error** と **(b) 画面右上の global toast** の併用を基本とする。

| 表示チャネル | 用途 | auto-dismiss |
| --- | --- | --- |
| inline error (操作要素直下に赤地 small text) | 直前操作の失敗理由を文脈付きで提示。フォーカスを保持しやすい | しない (操作再試行 / 別操作で消える) |
| global toast (画面右上、`<Toast>` placeholder) | 操作元から離れた箇所で発生したエラー、または短時間で消えてよい要約通知 | 5 秒 (操作要操の通知は permanent 寄り、bg 失敗は短く) |
| inline + toast 併用 | apply / restore / export 等の主要操作の失敗。inline で原因明示 + toast で「保存に失敗しました」要約 | toast のみ 5s、inline は明示 dismiss まで残す |

**文言指針**:

- 技術詳細ではなく行動指針を含める (例: 「Disk full のため保存できませんでした。空き容量を確保してから [再試行] してください」)
- 二段構造: 1 行目で何が起きたか / 2 行目で次の行動 (inline で 2 行、toast は 1 行に圧縮)
- i18n キー素のまま (例: `error.apply.failed`) は禁止

**アンチパターン**: `console.error` のみで UI に出さない / `alert()` で flow を強制停止する / エラー内容を握りつぶして success 扱いにする。

**ErrorModal との分離 (#614)**: `ErrorModal` は **想定外エラー (Rust panic / unhandled JS exception / React 内部例外) 専用** で、`isRecoverable=false` がデフォルト。recoverable error (`load_metadata` の I/O 失敗、`apply_changes` のネットワーク失敗等) は **本節で規定する inline + toast** に流す。両者は排他で、同一画面内に重複しない。詳細は [`ui-architecture.md` §4 エラー伝搬フロー](ui-architecture.md#4-エラー伝搬フロー-614) を参照。

#### AppError `code` ベースの分岐ルール (#663)

Tauri command 失敗時の error 表示は以下を厳守する:

1. `appErrorCodeIs(e, 'state.mtime_conflict')` で apply path → ConflictModal (modal 表示)
2. その他の AppError code → inline error
   - catch path で `toErrorState(e)` により `ErrorState { message, hint, code }` に正規化 (#694)
   - 1 行目: `errorState.message` (赤系: `var(--ae-danger)` ないし screen 固有 error 色)
   - 2 行目: `errorState.hint` を `<InlineErrorHint hint={...} />` component で表示
     (PR #693 で共通化、`💡` prefix + `var(--ae-text-dim)` を 1 箇所に集約。
     詳細は [ui-architecture.md §4.7](ui-architecture.md#§47-inlineerrorhint-component-693) 参照)
3. catch ブロック以外で error を扱わない (`alert()` / `console.error` のみは禁止)
4. globalErrorListener が拾うのは uncaught (window.error / unhandledrejection /
   panic) のみ。catch 済 Tauri command error は ErrorModal に出さない (規約)

#### §1.5.1 ConflictModal の hint slot 規約 (#695、C 案)

`state.mtime_conflict` の ConflictModal では、AppError hint を主表示し、modal
局所文言 (キャンセル ボタン挙動説明) は補足 1 行として別 paragraph に表示する規約:

- 1 行目 (`<p>{conflictError}</p>`): AppError.message を danger 色で表示
- 2 行目 (`<InlineErrorHint hint={conflictErrorHint} />`): AppError.hint を `💡`
  prefix + `var(--ae-text-dim)` で表示 (hint null 時は非表示)
- 3 行目 (`<p>{cancel 補足}</p>`): 「「キャンセル」で何もせずこのモーダルを閉じます。」
  を常時表示 (modal 局所文言、上書き / リロード の挙動は AppError hint がカバー)

旧 compose hint (3 button 全説明) は削除済 (PR #695)。AppError hint と modal
文言の重複を避けるため、modal 局所文言は modal-only な action (キャンセル 等) に
限定する規約。

### 1.6 ファイルパス表示の原則 (#676)

**原則**: ユーザーが現在扱っている動画ファイルを「どのフォルダのどのファイルか」識別できるよう、
5 画面 (drop / detecting / complete / preview / export) のすべての主要表示領域で
**絶対 path** を可視化する。fileName だけの表示は禁止 (同名ファイル区別不能のため)。

| 観点 | 規定 |
| --- | --- |
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

## 2. 画面別 UI 部品状態機械

§2 は 5 画面それぞれを **1 画面 = 1 PR** で順次追加する (#590 着手フローに従う)。

| 節 | 画面 | 主要 UI 部品 | 進捗 |
| --- | --- | --- | --- |
| §2.1 | drop | D&D zone / [参照…] / 直近録画リスト / SelectedCard (詳細設定パネル含む、#613) / probeError card | #598 で追加 |
| §2.2 | detecting | AllaganSigil 回転 / Header / progressBadge / PhaseRow ×2 / live log / [中断] | #600 で追加 |
| §2.3 | complete | statusDot / sourceBox / stats / [元に戻す] / [境界を調整] / [全試合書き出し] / [× 閉じる] / BrightnessTimeline / listItem / previewPane / emptyNote | #603 で追加 |
| §2.4 | preview | [◀ 一覧へ] / match name input / type select / Pane (×2 IN/OUT) / Pane.video / Pane.tcInput / stepRow ×6 / keyHint / FrameStrip / [適用] / dirty indicator / applyError / [元に戻す] / [書き出し] / emptyNote | #605 で追加 |
| §2.5 | export | [◀ プレビュー] / header / 出力先 input + [参照…] / 命名規則 input / コーデック selector ×2 / errorMessage / progressBox / [書き出し開始] / [中断] / [✓ フォルダを開く] + openFolderError / [設定変更して再書き出し] / [設定変更して再試行] / listHeader + bulk / listItem / emptyNote | 本 PR で追加 |

各部品節の記述フォーマット (canonical):

```text
#### §2.X.N <部品名>

| 項目 | 内容 |
|---|---|
| 種類 | button / input / select / list item / drop zone / progress bar / card / etc |
| 状態 | <部品ごとの enum、phase との対応関係を併記> |
| 遷移トリガー | <reducer event 名 (例: `BROWSE_CLICKED`) または UI イベント> |
| store mutation | <appStateStore / metadataStore のメソッド呼び出し、なければ「なし」> |
| 例外 / edge case | <該当 §1 共通原則の番号 + 個別注記> |
```

状態名・イベント名は **コードと 1:1 対応** させる ([drop reducer](../gui/src/screens/reducers/drop.ts) 等の event 名・phase 名をそのまま使う)。doc 上の文言は `code span` で表記し grep 可能にする。

### §2.1 drop

**phase**: `idle | selecting | probing | selected | probeError` ([reducers/drop.ts:21-48](../gui/src/screens/reducers/drop.ts#L21))

**store**: drop screen は **`metadataStore` を触らない** (metadata.json はまだロードしていない段階)。`appStateStore.setSelectedVideoPath(path)` で実 path を確定し、`appStateStore.navigate('detecting')` で遷移する。`metadataStore.loadSample()` 等は detecting 完了後の load シーケンスで発火する。

**dirty / silent loss**: 編集対象 metadata がないため §1.3 silent loss confirm の対象外。

**sample mode**: drop screen 自身が sample mode (`filePath === null`) を解除する起点なので、§1.4 read-only 制約の対象外。

**エラー表示**: §1.5 のうち本画面では **inline (phase=probeError card で画面メイン領域を置換)** を採用する。toast は使わない (probe 失敗は drop で完結する短い vertical flow であり、操作元から離れた箇所への影響がない)。

#### §2.1.1 D&D zone

| 項目 | 内容 |
| --- | --- |
| 種類 | drop zone (div、Tauri webview `onDragDropEvent` 購読 + HTML5 D&D fallback。[#568](https://github.com/Idios/kobutachan-allaganeye/issues/568) で実装) |
| 状態 | `idle` (待受、gold 破線) / `over-valid` (cyan 破線 + 薄背景、受付可能拡張子の drag-over 中) / `over-invalid` (danger 破線 + `⊘` icon + 「非対応形式 (.mp4 / .mkv / .avi / .mov のみ)」 inline、非対応形式の drag-over 中) / `disabled` (phase=`selecting/probing/selected/probeError` 時は drag を ignore、視覚不変) |
| 遷移トリガー | Tauri webview `onDragDropEvent` (drop 種別) → 拡張子 validation pass → reducer `DND_DROPPED` → phase `idle → probing` → probe → `selected/probeError`。HTML5 経路は jsdom テスト fallback (`dragDropEnabled: true` (default) のため実機では Tauri が intercept して発火しない) |
| store mutation | drop 経路は drop 後に `[OK — 検知開始]` 確定で `setSelectedVideoPath(path)` (`§2.1.6 [OK]` と同経路) |
| 例外 / edge case | 拡張子は大文字小文字非区別 (`.mp4 / .mkv / .avi / .mov`)、複数ファイル drop は最初の valid 拡張子 1 件のみ採用、フォルダ drop は拡張子マッチなしで自動 reject (`probeFn` 未呼出 + phase 不変)。drag-over 中の拒否表示は drop zone 内 inline (toast なし)、drag-leave で復帰。`phase !== 'idle'` 時は drag を ignore (probing 中の干渉防止) |

#### §2.1.2 [参照…] button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([DropScreen.tsx:147-154](../gui/src/screens/DropScreen.tsx#L147)) |
| 状態 | `idle` (phase=`idle/probeError`) / `disabled` (phase=`selecting/probing/selected`) |
| 遷移トリガー | `onClick` → `pickAndProbe()` → reducer `BROWSE_CLICKED` (phase=`idle → selecting`) または `BROWSE_CLICKED` (phase=`probeError → selecting`) |
| store mutation | probe 成功時のみ `appStateStore.setSelectedVideoPath(path)` (この時点ではまだ呼ばれない、§2.1.6 [OK] で発火) |
| 例外 / edge case | 1.2 disabled 理由: selecting 中は `(選択中)` inline テキスト ([:155](../gui/src/screens/DropScreen.tsx#L155))、probing 中は `(解析中)` ([:156](../gui/src/screens/DropScreen.tsx#L156)) を併記。**現状 tooltip は未実装** — §1.2 準拠として `aria-describedby` + `title` を後続 PR で追加 (本 doc が source of truth) |

#### §2.1.3 直近の録画 list (#571)

| 項目 | 内容 |
| --- | --- |
| 種類 | list (各 item は `<button>`、`recentStore.entries` から render) |
| 状態 | `idle` (phase=`idle`) / `disabled` (phase=`selecting/probing/selected/probeError`) |
| 遷移トリガー | `onClick` → `selectRecent(item)` → reducer `RECENT_PICKED` (phase=`idle → probing`) → `probeAndDispatch(item.path)`。drop と同じ probe 経路を辿るので、metadata 不整合 / 解像度差異もそこで再評価される |
| store mutation | mount 時に `recentStore.load()` で `<install dir>/recent.json` (PR #655 Round 2: Portable ZIP 哲学に揃えて exe ディレクトリ配置) をロード。probe 成功時に `recentStore.add(path)` で履歴更新 (重複は最新化、最大 10 件、`\\?\` extended-length prefix は Rust 側で strip) |
| 例外 / edge case | (1) 履歴ゼロ件: 「履歴はまだありません」placeholder ([recent-empty](../gui/src/screens/DropScreen.tsx))。(2) ファイル不在: Rust `read_recent` / `add_recent` が `Path::exists()` で確認し、不在 entry を**自動 prune** + 永続化更新 (PR #655 Round 2: 旧 grayed-out + warning notice UX を撤廃)。(3) `recent.json` 破損: 空配列扱い (`read_recent_sync` が `unwrap_or_default`、Rust 側)。(4) 同 path 再選択: dedup でトップに移動 + mtime / addedAt 更新 (Windows は case-insensitive + separator-insensitive 比較)。(5) `read_recent` / `add_recent` の Tauri command 自体が AppError で reject された場合 (Rust 側の I/O 例外等): `recentStore.loadError` / `addError` に message + `loadErrorHint` / `addErrorHint` に AppError hint がセットされ、`recentHeading` 直後に inline notice (`<InlineErrorHint>` 経由、`role="alert"` + `data-testid="recent-notice"`) を表示。`loadError` 優先、両 null で非表示、dismiss なし、次回 load/add 成功で自動消去 (#698 A-minimal、PR #733) |
| 表示 | 各 item は `[◈] [full path] [date] [GB]` の row。長い path は CSS の `direction: rtl` truncate で**左側を `…` で省略**して file-name 末尾を常に可視に保つ。hover で title tooltip にフルパス |

#### §2.1.4 SelectedCard (probe 結果カード)

| 項目 | 内容 |
| --- | --- |
| 種類 | card (display container、phase=`selected` のときのみ render、[DropScreen.tsx:198-232](../gui/src/screens/DropScreen.tsx#L198)) |
| 状態 | `selected` (probe 結果 + 確認ボタン表示) |
| 遷移トリガー | reducer `PROBE_OK` で phase=`probing → selected` 後に出現 |
| store mutation | カード自体は表示のみ、mutation なし (ボタンは §2.1.5 / §2.1.6) |
| 例外 / edge case | `probeInfo` が null になり得るが、phase=`selected` 時は guard ([:115-116](../gui/src/screens/DropScreen.tsx#L115)) で render しないため不整合は発生しない。**§1.6 ファイルパス表示の原則に準拠** — `info.path` を `splitPath()` で分解、primary `.selectedName` (fileName) + secondary `.pathSecondary` (parentDir 左側省略) + container `title={info.path}` の 2 段構造 (`data-testid="drop-selected-path"`、#676) |

#### §2.1.5 [キャンセル] button (SelectedCard 内)

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([DropScreen.tsx:223-225](../gui/src/screens/DropScreen.tsx#L223)) |
| 状態 | `idle` (phase=`selected` のみ表示) |
| 遷移トリガー | `onClick` → `cancelSelection()` → reducer `CANCEL_SELECTION` (phase=`selected → idle`) + `setProbeInfo(null)` |
| store mutation | なし (`appStateStore.setSelectedVideoPath` は §2.1.6 でしか呼ばれていないので、リセットも不要) |
| 例外 / edge case | confirm ダイアログなし (まだ §1.3 dirty 編集なし)。D&D 経由 selection も同 phase (`selected`) に集約済み (§2.1.1 D&D zone → reducer `DND_DROPPED` → `PROBE_OK` → `selected` で SelectedCard 共通経路、[#568](https://github.com/Idios/kobutachan-allaganeye/issues/568) で実装) |

#### §2.1.6 [OK — 検知開始] button (SelectedCard 内)

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([DropScreen.tsx:226-228](../gui/src/screens/DropScreen.tsx#L226)) |
| 状態 | `idle` (phase=`selected` のみ表示。`probeInfo` が null の場合は `confirm()` 内で early return しているが、本ボタン自体は disabled にしていない — 不整合シナリオを防ぐ最終 guard として機能) |
| 遷移トリガー | `onClick` → `confirm()` → `appStateStore.setSelectedVideoPath(probeInfo.path)` + `navigate('detecting')` |
| store mutation | `appStateStore.setSelectedVideoPath(path)` ([DropScreen.tsx:73](../gui/src/screens/DropScreen.tsx#L73)) + `appStateStore.navigate('detecting')` ([:74](../gui/src/screens/DropScreen.tsx#L74)) |
| 例外 / edge case | navigate 後の detecting 画面で metadata.json load を行うため、本ボタン押下時点ではまだ `metadataStore` は触られていない。`probeInfo` 不整合時は `confirm()` 内で no-op |

#### §2.1.7 probeError card

| 項目 | 内容 |
| --- | --- |
| 種類 | card (display container、phase=`probeError` のときのみ render、[DropScreen.tsx:117-137](../gui/src/screens/DropScreen.tsx#L117))。`role="alert"` で a11y 通知 |
| 状態 | `probeError` (error 表示 + dismiss / retry ボタン) |
| 遷移トリガー | reducer `PROBE_FAIL` で phase=`probing → probeError` 後に出現 ([DropScreen.tsx:53,67](../gui/src/screens/DropScreen.tsx#L53)) |
| store mutation | カード自体は表示のみ |
| 例外 / edge case | error メッセージは `setError(e.message)` ([:52,66](../gui/src/screens/DropScreen.tsx#L52)) で local state に保存。dialog open 失敗 (file picker plugin のエラー) と probe 失敗 (ffprobe エラー) のいずれもこの card に集約。§1.5 文言指針に従い、ffprobe からの raw stderr ではなく行動指針付きで wrap することが望ましい (現状 raw メッセージ — 後続改善で wrap、本 doc が source of truth) |

#### §2.1.8 [閉じる] button (probeError card 内)

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([DropScreen.tsx:122-128](../gui/src/screens/DropScreen.tsx#L122)) |
| 状態 | `idle` (phase=`probeError` のみ表示) |
| 遷移トリガー | `onClick` → `dismissError()` → reducer `DISMISS_ERROR` (phase=`probeError → idle`) + `setError(null)` |
| store mutation | なし |
| 例外 / edge case | confirm ダイアログなし (編集なし)。idle に戻ると D&D zone と [参照…] が再度有効化される |

#### §2.1.9 [再試行] button (probeError card 内)

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([DropScreen.tsx:129-135](../gui/src/screens/DropScreen.tsx#L129)) |
| 状態 | `idle` (phase=`probeError` のみ表示) |
| 遷移トリガー | `onClick` → `pickAndProbe()` → reducer `BROWSE_CLICKED` (phase=`probeError → selecting`) |
| store mutation | なし (probe 成功時の流れは §2.1.2 と同じ) |
| 例外 / edge case | 連続失敗時も常に [閉じる] で `idle` に戻れる。`pickAndProbe()` 内で `setError(null)` するので前回 error は消える |

#### §2.1.10 詳細設定パネル (DetectionParamsPanel、SelectedCard 内)

[#613](https://github.com/Idios/kobutachan-allaganeye/issues/613) で追加。SelectedCard (phase=`selected`) の meta 表 と `[OK]/[キャンセル]` actions の間に collapsible で配置 ([DetectionParamsPanel.tsx](../gui/src/screens/DetectionParamsPanel.tsx))。

**目的**: `start_detect` (#569) に渡す検知パラメータを GUI 上で調整。値は `appStateStore.detectionParams` に保存され、`reset()` まで session 中保持される (localStorage 永続化なし、再起動時は default に戻る)。

**スコープ (3 パラメータ)**: `blackout_threshold` / `workers` / `gpu`。`--no-audio` は audio module frozen (#327、`split_matches.py:525`) のため UI 不公開、#327 解凍後に再追加する。

| 項目 | 内容 |
| --- | --- |
| 種類 | collapsible panel (`<button aria-expanded={open} aria-controls={bodyId}>` header + 折り畳まれた body の `<div id={bodyId}>`) |
| 状態 | `collapsed` (default、初期表示) / `expanded` (header click で toggle) |
| 遷移トリガー | header `onClick` → local `setOpen` で toggle (store には影響なし) |
| store mutation | 各 control が `setDetectionParams({...})` で patch、`[リセット]` で `resetDetectionParams()` |
| 例外 / edge case | collapsed 時に default 以外の値があれば header 横に「(変更あり)」 hint を表示。`reset()` (アプリ全体の reset) からも default に戻る |

##### §2.1.10.1 [▶ 詳細設定] / [▼ 詳細設定] header toggle

| 項目 | 内容 |
| --- | --- |
| 種類 | button (`aria-expanded` / `aria-controls` 属性付き) |
| 状態 | `collapsed` (▶) / `expanded` (▼) |
| 遷移トリガー | `onClick` → local `setOpen((v) => !v)` |
| store mutation | なし |
| 例外 / edge case | collapsed + 値が default と異なる場合のみ `(変更あり)` chip を表示 (`<span aria-label="変更あり">`) |

##### §2.1.10.2 検知しきい値 slider (blackoutThreshold)

| 項目 | 内容 |
| --- | --- |
| 種類 | `<input type="range" min={0} max={50} step={1}>` + 値表示 |
| 状態 | 0-50 (CLI 仕様は 0-255 だが UI では実用域 0-50 に絞る、default 15) |
| 遷移トリガー | `onChange` → `setDetectionParams({ blackoutThreshold: number })` |
| store mutation | `appStateStore.detectionParams.blackoutThreshold` |
| 例外 / edge case | スライダ値はそのまま `start_detect` の `params.blackoutThreshold` として渡る (default 値 15 でも CLI は `--blackout-threshold 15` flag を構築する。実害なし) |

##### §2.1.10.3 ワーカー数 numeric input (workers)

| 項目 | 内容 |
| --- | --- |
| 種類 | `<input type="number" min={0} max={32} step={1}>` + `(自動)` hint (workers===0 のみ) |
| 状態 | 0 (auto) / 1-32 (explicit) |
| 遷移トリガー | `onChange` → `setDetectionParams({ workers: number })` (`Number.isFinite` ガード付き) |
| store mutation | `appStateStore.detectionParams.workers` |
| 例外 / edge case | `0` は UI 上の auto sentinel。`toStartDetectParams` で `workers: 0` → `null` に変換され、Rust 側 `DetectParams.workers: None` で `--workers` flag が省略される ([detection.ts:23-29](../gui/src/utils/detection.ts#L23)) |

##### §2.1.10.4 GPU tri-state 選択 (gpu)

| 項目 | 内容 |
| --- | --- |
| 種類 | button group (`role="radiogroup"` + 3 つの `role="radio"`) |
| 状態 | `自動` (gpu=null、CLI omit) / `ON` (gpu=true、`--gpu`) / `OFF` (gpu=false、`--no-gpu`) |
| 遷移トリガー | 各 button `onClick` → `setDetectionParams({ gpu: null \| true \| false })` |
| store mutation | `appStateStore.detectionParams.gpu` |
| 例外 / edge case | radiogroup pattern (`aria-checked` で active state を表現)。Rust 側 `DetectParams.gpu` が 3 値 `Option<bool>` を解釈し排他 flag に変換 |

##### §2.1.10.5 [リセット] button

| 項目 | 内容 |
| --- | --- |
| 種類 | button (panel body 末尾、右寄せ) |
| 状態 | params == default のとき `disabled` (押下不可) / それ以外で active |
| 遷移トリガー | `onClick` → `resetDetectionParams()` (全 3 フィールドを `DEFAULT_DETECTION_PARAMS` に戻す) |
| store mutation | `appStateStore.detectionParams` 全体を default に上書き (`selectedVideoPath` など他の state は触らない) |
| 例外 / edge case | disabled 判定は `isDetectionParamsModified` ([utils/detection.ts](../gui/src/utils/detection.ts)) が三フィールドを default と等値判定で行う。`aria-label` に default 値を含める (例: `"reset to defaults (blackout 15, workers auto, gpu auto)"`) |

##### §2.1.10.6 styling / a11y / Tab order

- styling: 既存 ExportScreen の field/value pattern (`fieldLabel` + 入力要素) と同系統。色は token (`var(--ae-gold-dim)` / `var(--ae-cyan)` / `var(--ae-text)`) を再利用、新規追加なし
- a11y:
  - header: `aria-expanded` / `aria-controls` で expand 状態を AT に通知
  - 各 input: `<label htmlFor>` (slider / numeric) で関連付け、tri-state は `aria-label="gpu mode"` + `role="radio"`
  - リセット button: `aria-label` で disabled 理由 (default 値) を明示
- Tab order: header toggle → (展開時) blackout slider → workers numeric → gpu (auto/on/off の 3 button) → reset button → SelectedCard `[キャンセル]` → `[OK]`。drop flow 全体で natural forward tab を保つ
- **`--no-audio` UI 不採用**: `allaganeye/commands/split_matches.py:525` で audio module は frozen 状態 (#327) のため `--no-audio` flag は実質 no-op。GUI 側でのみ控え (Rust `DetectParams.no_audio` field 自体は #569 で実装済み、#327 解凍時に再公開)

### §2.2 detecting

**phase**: `running | cancelling | cancelled | completed | error` ([reducers/detecting.ts:16-40](../gui/src/screens/reducers/detecting.ts#L16))

**store**: detecting screen は Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) で **`metadataStore.load(metadata_path)` を `start_detect` resolve 後に 1 回呼ぶ** 動作に切替済。`selectedVideoPath` が null の StateSwitcher dev mode 経路でのみ `loadSample()` にフォールバックする。`appStateStore.navigate('drop' | 'complete')` で遷移し、`selectedVideoPath` は読むのみで mutation しない (drop で確定した path を後段が継承する設計、#465 review C)。

**dirty / silent loss**: 編集対象 metadata が無いため §1.3 silent loss confirm の対象外。ただし [中断] → drop 遷移は確定済み video path を捨てる動線なので、確認 dialog を入れるかは検討事項として残す (Phase 2.5 [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) では未対応、後続で議論)。

**sample mode**: Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) で実 CLI 結果への切替が完了し、本画面の `loadSample()` 経路は **`selectedVideoPath` が null の StateSwitcher dev mode 専用フォールバック** に縮退した。プロダクションフロー (drop → detecting) では呼ばれない。

**エラー表示**: §1.5 のうち本画面では現状 **toast を使わず drop へ navigate する暫定挙動**。Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) は CLI stdout streaming への差し替えまでで、`error` phase 時の **toast 通知** は [#614](https://github.com/Idios/kobutachan-allaganeye/issues/614) (panic / error / log 構造化) で `ErrorBoundary` / `ErrorModal` 兼任設計と合わせて実装する。本画面では inline は採用しない (画面が観測フローに専念する設計のため)。

**実装段階**:

- Phase 2 (#464): 80ms × 100 tick = 8s の dummy progress、log は progress 連動の hardcoded 3 行 (実装当時)
- Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) **済**: 実 CLI (`allaganeye detect --progress-format json`) stdout streaming に差し替え、log は CLI 1 行 = 1 entry で逐次 append、最大 80 行で truncate、phase 別に `info` / `done` / `error` / `warn` の kind 色分け。meta 行は `probing` event の ffprobe 結果 (`width × height` / `fps` / `codec` / `duration`) に差し替え。`cancelling → cancelled` は **[中断] で `kill_tracked_processes` を invoke し、走行中の detect (Python CLI + ffmpeg 子) を reap してから確定** する ([#813](https://github.com/Idios/kobutachan-allaganeye/issues/813))。kill インフラ自体は [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) / [#756](https://github.com/Idios/kobutachan-allaganeye/issues/756) (Job Object) で配線済で、#813 は detect cancel path への接続。旧 run の straggler event は `start_detect` が払い出す run id を全 `detect-progress` payload に echo し、listener が現在 run id 以外を無視する fence で遮断する (audit P1-1)
- 関連: [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) (running 中の `× 閉じる` 確保) は本画面の cancel と同じ `kill_tracked_processes` 経路を共有する

#### §2.2.1 AllaganSigil (回転アニメーション)

| 項目 | 内容 |
| --- | --- |
| 種類 | 装飾 SVG ([DetectingScreen.tsx:85](../gui/src/screens/DetectingScreen.tsx#L85)、`<AllaganSigil size={84} rotating={phase === 'running'} />`) |
| 状態 | `displayOnly`。phase=`running` のみ回転、それ以外は静止 |
| 遷移トリガー | phase 変化に追従 (props `rotating` の derived value) |
| store mutation | なし |
| 例外 / edge case | アニメーション停止は phase 終端 (cancelled / completed / error) への到達を視覚的に通知する役割。a11y は `role` 未指定 (装飾扱い) |

#### §2.2.2 Header (caption / fileName / meta)

| 項目 | 内容 |
| --- | --- |
| 種類 | display block ([DetectingScreen.tsx:84-97](../gui/src/screens/DetectingScreen.tsx#L84)) |
| 状態 | `displayOnly` |
| 遷移トリガー | なし。`selectedVideoPath` 変化時に再 render (basename を抜き出して表示) |
| store mutation | なし |
| 例外 / edge case | `selectedVideoPath` が null の場合は fileName `'(video)'` フォールバック (parentDir は空文字列で secondary 行非表示)。Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) で `meta` 行を `probing` event payload (`width` × `height` / `fps` / `codec` / `duration_s`) から実 ffprobe 結果に差し替え済 (`probing` 受信前の数百 ms は暫定 `phase: …` を表示)。**§1.6 ファイルパス表示の原則に準拠** — `selectedVideoPath` を `splitPath()` で分解、primary `.fileName` (14px) + secondary `.pathSecondary` (parentDir 左側省略) + container `title={selectedVideoPath}` (`data-testid="detecting-path"`、#676) |

#### §2.2.3 progressBadge

| 項目 | 内容 |
| --- | --- |
| 種類 | display block ([DetectingScreen.tsx:91-96](../gui/src/screens/DetectingScreen.tsx#L91)) |
| 状態 | `displayOnly`。`progress` (0-100) を四捨五入で表示 |
| 遷移トリガー | local state `progress` 変化 (Phase 2 dummy interval、Phase 2.5 で CLI 進捗イベント) |
| store mutation | なし |
| 例外 / edge case | Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) で `progressTiming` 行を経過時間 (`fmtElapsed(elapsed)`) と簡易 ETA (`computeEta(percent, elapsed)` の線形外挿、進捗 0% / 100% 付近では非表示) に差し替え済 |

#### §2.2.4 PhaseRow.Detecting (粗スキャン)

| 項目 | 内容 |
| --- | --- |
| 種類 | progress bar ([DetectingScreen.tsx:102-107](../gui/src/screens/DetectingScreen.tsx#L102)、`PhaseRow` コンポーネント) |
| 状態 | bar fill: `pending` (pct=0) / `running` (0<pct<100) / `done` (pct≥100) ([DetectingScreen.tsx:156-178](../gui/src/screens/DetectingScreen.tsx#L156))。phase との対応は無く `pct1` (progress × 1.25) のみで決まる |
| 遷移トリガー | `progress` 変化 (Phase 2 dummy、Phase 2.5 で CLI のフェーズ進捗) |
| store mutation | なし |
| 例外 / edge case | Phase 2 では `pct1` が 80% 時点で 100% 完了する見せ方 (粗スキャンは早く終わる演出)。Phase 2.5 で実フェーズに対応する pct 計算に差し替え |

#### §2.2.5 PhaseRow.Refining (精密計測)

| 項目 | 内容 |
| --- | --- |
| 種類 | progress bar ([DetectingScreen.tsx:108-113](../gui/src/screens/DetectingScreen.tsx#L108)、`PhaseRow` の 2 個目) |
| 状態 | `pending` / `running` / `done` (§2.2.4 と同じ semantics) |
| 遷移トリガー | `progress` 変化 (Phase 2 dummy では `pct2 = (progress - 40) × 1.67`、progress=40 から開始) |
| store mutation | なし |
| 例外 / edge case | Phase 2 では Detecting 完了相当のタイミング (progress=40) から start。Phase 2.5 で実フェーズ境界に置換 |

#### §2.2.6 live log

| 項目 | 内容 |
| --- | --- |
| 種類 | append-only display list ([DetectingScreen.tsx:118-133](../gui/src/screens/DetectingScreen.tsx#L118))。`role="log"` + `aria-label="detect log"` で a11y 対応 |
| 状態 | `displayOnly`。Phase 2 は progress 閾値 (0% / 30% / 60%) で 3 行を順次表示する hardcoded 動作 |
| 遷移トリガー | progress 連動 (Phase 2 dummy)。Phase 2.5 で CLI stdout 行を逐次 append |
| store mutation | なし |
| 例外 / edge case | Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) で実 CLI stdout 1 行 = 1 entry の append に切替済。`MAX_LOG_LINES = 80` で先頭から truncate、retention は描画にのみ影響し store には永続化しない。phase 別に `info` / `done` / `error` / `warn` の `kind` を CSS class (`logEntryDone` / `logEntryError` / `logEntryWarn`) で色分け (キーワード視認性確保) |

#### §2.2.7 [中断] button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([DetectingScreen.tsx:136-143](../gui/src/screens/DetectingScreen.tsx#L136)) |
| 状態 | `idle` (phase=`running`) / `disabled` (phase=`cancelling/cancelled/completed/error`) |
| 遷移トリガー | `onClick` → reducer `CANCEL_CLICKED` (phase=`running → cancelling`)。`cancelling` phase の副作用 effect が `kill_tracked_processes` を invoke (失敗は `console.error` のみ、best-effort) → 完了後に `CANCEL_CONFIRMED` を発火し `cancelling → cancelled` 遷移 ([#813](https://github.com/Idios/kobutachan-allaganeye/issues/813))。kill が in-flight `start_detect` を reap すると Rust 側 `untrack_child` が None を返し `subprocess.cancelled` で reject、reducer が `DETECT_ERROR during cancelling → cancelled` で吸収するため error 画面化しない |
| store mutation | なし (cancelled 検出後の effect で `appStateStore.navigate('drop')` のみ) |
| 例外 / edge case | §1.2 disabled 理由表示について、現状 `disabled={phase !== 'running'}` のみで tooltip / inline hint 未実装 → 後続 PR で `title="検知実行中のみ中断できます"` 等を追加 (本 doc が source of truth)。`cancelling` 中の連打は disabled で物理的に防止 |

#### §2.2.8 Detecting error view path display (#676)

| 項目 | 内容 |
| --- | --- |
| 種類 | display block ([DetectingScreen.tsx:732-792](../gui/src/screens/DetectingScreen.tsx#L732) `DetectingErrorView` 内、`role="alert"` の error card 内部) |
| 状態 | `displayOnly`。phase=`error` のときのみ render される (error view) |
| 遷移トリガー | なし。`selectedVideoPath` 由来の `displayPath` prop に追従 |
| store mutation | なし |
| 例外 / edge case | **§1.6 ファイルパス表示の原則に準拠** — `selectedVideoPath` を `splitPath()` で分解、primary `.errorFile` (13px / text-bright) + secondary `.pathSecondary` (parentDir 左側省略) + container `title={selectedVideoPath}` (`data-testid="detecting-error-path"`)。`selectedVideoPath` が null の場合は fileName `'(video)'` + secondary 行非表示にフォールバック |

### §2.3 complete

**phase**: 専用 reducer なし。`metadataStore` と `appStateStore.selectedMatchIndex` の組合せで暗黙的に状態を表現する。便宜上の状態名:

- `complete_empty` — `metadata === null` (emptyNote 表示)
- `complete_idle` — metadata あり、操作待機
- `complete_restoring` — RestoreButton が in-flight (`metadataStore.restoring=true`)

**store**: 主に **読み取り** (`metadata` / `selectedMatchIndex` / `selectedVideoPath` / `hasBackup`)。書き込みは `selectMatch` (listItem / BrightnessTimeline 選択)、`openPreviewFor` ([境界を調整] / listItem 双 click)、`navigate` ([全試合書き出し] / [× 閉じる])、`metadataStore.clear` ([× 閉じる])、`appStateStore.reset` ([× 閉じる])。`metadataStore.restore` は RestoreButton 経由 (§2.3.4)。

**dirty / silent loss**: §1.3 dirty consume 表に従う。complete 画面で dirty=true (preview から戻った直後等) 状態の consume 経路:

- `[× 閉じる]` → `clear()` + `reset()` + drop: **confirm 必須** (現状未実装、後続で対応)
- 別 match double-click / `[境界を調整]` → preview: **confirm 必須** (現状未実装、後続で対応)
- `[全試合書き出し]` → export: **confirm 必須** (現状未実装、後続で対応)
- `[元に戻す]` (RestoreButton): 自前で confirm dialog を持つ ([RestoreButton.tsx:42-50](../gui/src/components/RestoreButton.tsx#L42))

**sample mode**: `metadataStore.filePath === null` の sample mode では `[元に戻す]` は `hasBackup=false` で disabled、complete 画面では `SampleModeBanner` を上部 `topBar` 直下に表示する ([#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で実装済)。

**エラー表示**: §1.5 inline + toast 併用。complete 画面の主要エラー源は `restoreError` ([RestoreButton.tsx:63-67](../gui/src/components/RestoreButton.tsx#L63), inline `role="alert"`)。global toast 兼任設計は [#614](https://github.com/Idios/kobutachan-allaganeye/issues/614) (panic / error / log 構造化、`ErrorBoundary` / `ErrorModal`) で実装する。

**実装段階**:

- Phase 2 (#464): 試合一覧 / BrightnessTimeline / プレビューサムネイル ([#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) で実 path に切替済) が動作。`brightness` は `sampleBrightness()` の固定波形だった
- Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) **済**: `metadata.brightness_samples?.values` (CLI が Pass 1 から 512 点に間引いて metadata.json に埋め込む `BrightnessSamples` 構造) を優先利用、欠落時のみ `sampleBrightness()` フォールバック
- 後続: 所要列 ([#586](https://github.com/Idios/kobutachan-allaganeye/issues/586))、a11y / polish ([#587](https://github.com/Idios/kobutachan-allaganeye/issues/587))、threshold 連動 ([#588](https://github.com/Idios/kobutachan-allaganeye/issues/588))、§1.3 dirty consume confirm 全経路

#### §2.3.1 statusDot

| 項目 | 内容 |
| --- | --- |
| 種類 | 装飾 (`<div aria-hidden="true">`、[CompleteScreen.tsx:65](../gui/src/screens/CompleteScreen.tsx#L65)) |
| 状態 | `displayOnly` |
| 遷移トリガー | なし (常時可視) |
| store mutation | なし |
| 例外 / edge case | 常時 gold 点。Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) で「sample mode は別色」「dirty 時は瞬き」等の議論余地あり (本 doc 範囲外、議論時は §1.4 / §1.3 と整合させる) |

#### §2.3.2 sourceBox (caption + filename)

| 項目 | 内容 |
| --- | --- |
| 種類 | display block ([CompleteScreen.tsx:66-69](../gui/src/screens/CompleteScreen.tsx#L66)) |
| 状態 | `displayOnly`。`metadata.source` を full path で表示 |
| 遷移トリガー | `metadata` 変化に追従 |
| store mutation | なし |
| 例外 / edge case | **§1.6 ファイルパス表示の原則に準拠** — `videoSource` (= `selectedVideoPath ?? metadata.source`) を `splitPath()` で分解、primary `.sourceName` (13px / text-bright) + secondary `.pathSecondary` (parentDir 左側省略) + container `title={videoSource}` (`data-testid="complete-path"`、#676)。sample mode 等 `selectedVideoPath` 不在時は `metadata.source` にフォールバックして同一構造で表示 |

#### §2.3.3 stats (試合数 / 総尺)

| 項目 | 内容 |
| --- | --- |
| 種類 | display group ([CompleteScreen.tsx:70-81](../gui/src/screens/CompleteScreen.tsx#L70)) |
| 状態 | `displayOnly`。`metadata.matches.length` と `metadata.source_duration_display` を表示 |
| 遷移トリガー | `metadata` 変化に追従 |
| store mutation | なし |
| 例外 / edge case | `matches.length === 0` の場合 `0` 表示 (後段の listItem は空、previewPane は非表示 = §2.3.10)。Phase 2.5 で「合計試合長」「FL 比率」等の追加列が議論対象 ([#586](https://github.com/Idios/kobutachan-allaganeye/issues/586)) |

#### §2.3.4 [元に戻す] button (RestoreButton)

| 項目 | 内容 |
| --- | --- |
| 種類 | button + inline error ([RestoreButton.tsx:53-69](../gui/src/components/RestoreButton.tsx#L53)) |
| 状態 | `idle` (`hasBackup=true` && `restoring=false`) / `busy` (`restoring=true`、ラベル `…`) / `disabled` (`hasBackup=false` または `restoring=true`) |
| 遷移トリガー | `onClick` → `confirmFn(confirmMessage)` で確認 → OK なら `metadataStore.restore()` (atomic copy `metadata.original.json` → `metadata.json`) → 成功なら `onRestored?` callback |
| store mutation | `metadataStore.restoring`, `metadataStore.metadata` (再 load), `metadataStore.dirty=false` (apply の rollback として), `metadataStore.hasBackup` (`refreshBackupStatus`) |
| 例外 / edge case | confirm キャンセル → 何もしない。restore 失敗 → `restoreError` を inline `role="alert"` で表示。complete 画面では `onRestored` 未指定 (preview 画面は navigate('complete') を渡す)。§1.2 通り disabled 理由は priority 順: `restoring` → `isSample` (理由: 'サンプル動画では保存できません') → `!hasBackup` (理由: 'バックアップが存在しません') で tooltip + inline hint を表示 ([#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で実装済) |

#### §2.3.5 [境界を調整] button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([CompleteScreen.tsx:84-94](../gui/src/screens/CompleteScreen.tsx#L84)) |
| 状態 | `idle` (selectedMatch あり) / `disabled` (`!selectedMatch`、つまり `matches=[]`) |
| 遷移トリガー | `onClick` → `appStateStore.openPreviewFor(selectedMatch.index)` (内部で `selectMatch` + `navigate('preview')`) |
| store mutation | `appStateStore.selectedMatchIndex`, `appStateStore.screen='preview'` |
| 例外 / edge case | §1.3 dirty=true 時の confirm が現状未実装 (canonical: 「未保存の変更があります。破棄して別の試合を開きますか？」)。後続で `if (dirty) confirm(...)` を入れる必要あり。§1.2 disabled 理由 tooltip ("試合が選択されていません") は現状未実装 |

#### §2.3.6 [全試合書き出し] button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([CompleteScreen.tsx:95-101](../gui/src/screens/CompleteScreen.tsx#L95)) |
| 状態 | `idle` (現状無条件で活性) |
| 遷移トリガー | `onClick` → `navigate('export')` |
| store mutation | `appStateStore.screen='export'` |
| 例外 / edge case | `matches.length === 0` でも活性 (export 画面で空状態を扱う想定)、Phase 2.5 で「試合 0 件のときは disabled + 理由表示」とするかは [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) で議論。§1.3 dirty=true confirm が未実装、後続で実装 (canonical: 「未保存の変更があります。破棄して書き出しへ進みますか？」) |

#### §2.3.7 [× 閉じる] button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([CompleteScreen.tsx:102-109](../gui/src/screens/CompleteScreen.tsx#L102)) |
| 状態 | `idle` (現状無条件で活性) |
| 遷移トリガー | `onClick` → `handleClose()` ([CompleteScreen.tsx:56-60](../gui/src/screens/CompleteScreen.tsx#L56)) → `clear()` + `appReset()` + `navigate('drop')` |
| store mutation | `metadataStore` 全 reset、`appStateStore` 全 reset、`appStateStore.screen='drop'` |
| 例外 / edge case | §1.3 dirty=true 時の confirm が未実装。**現状 silent loss する** ([#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) 系の root cause)。canonical: 「未保存の変更があります。破棄してファイル選択へ戻りますか？」を後続で必須実装 |

#### §2.3.8 BrightnessTimeline (match block click)

| 項目 | 内容 |
| --- | --- |
| 種類 | SVG component ([BrightnessTimeline.tsx](../gui/src/components/BrightnessTimeline.tsx))。grid / threshold line / blackout bands / brightness line+fill / match blocks / time axis の合成 |
| 状態 | `displayOnly` (子要素 grid / threshold / blackouts / line / axis) + interactive (match blocks)。match block の visual: `selectedIndex` 一致で opacity=1 + stroke、それ以外で opacity=0.55 |
| 遷移トリガー | match block (`<g>`) `onClick` → `props.onSelectMatch(index)` → `appStateStore.selectMatch(index)` |
| store mutation | `appStateStore.selectedMatchIndex` |
| 例外 / edge case | `threshold` prop は現状 hardcoded default 15、Phase 2.5 ([#588](https://github.com/Idios/kobutachan-allaganeye/issues/588)) で `metadata.detection_params.blackout_threshold` 連動に置換予定。`samples` は Phase 2 で `sampleBrightness()` 固定、Phase 2.5 で実 video の brightness CSV / array に置換 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569))。selectedIndex の同期は listItem (§2.3.9) と双方向 |

#### §2.3.9 試合一覧 listItem (single + double click)

| 項目 | 内容 |
| --- | --- |
| 種類 | `<li>` ([CompleteScreen.tsx:128-160](../gui/src/screens/CompleteScreen.tsx#L128))。MatchThumb / 試合名 + 開始→終了 + duration / typeBadge (FL / ?) を内包 |
| 状態 | `idle` / `active` (selectedMatchIndex 一致時 `listItemActive` クラス + `data-selected="true"`) / `postMatch` (`post_match: true` 時 `listItemPostMatch` クラス (dimmed) + `data-post-match="true"` + badge「試合後」、[#805](https://github.com/Idios/kobutachan-allaganeye/issues/805) Phase 2) |
| 遷移トリガー | single `onClick` → `selectMatch(index)` (選択のみ) / `onDoubleClick` → `openPreviewFor(index)` (選択 + preview 遷移) |
| store mutation | single click: `appStateStore.selectedMatchIndex` のみ。double click: 加えて `appStateStore.screen='preview'` |
| 例外 / edge case | §1.3 dirty=true 時に別 match を double click すると編集破棄が発生 → confirm 必須 (現状未実装、§2.3.5 [境界を調整] と同等の対応)。listItem 内 typeBadge は表示専用で click 影響なし。`name` は `match.name ?? "MATCH_NNN"` フォールバック ([metadata-spec.md](metadata-spec.md) 編集契約により `name` は GUI 表示専用、metadata.json には書き戻さない) |

#### §2.3.10 previewPane (display)

| 項目 | 内容 |
| --- | --- |
| 種類 | display block ([CompleteScreen.tsx:165-208](../gui/src/screens/CompleteScreen.tsx#L165))。MatchThumb (large) + previewPlayOverlay + previewMeta (title + 開始 / 終了 / 長さ / 分類) |
| 状態 | `displayOnly` (selectedMatch 存在時のみ render、`!selectedMatch` で section 全体非表示) |
| 遷移トリガー | `selectedMatch` 変化に追従 (selectMatch / openPreviewFor / 1-match auto-select 経由) |
| store mutation | なし |
| 例外 / edge case | previewPlayOverlay は装飾のみで現状クリック無効 (preview 画面遷移は §2.3.5 / §2.3.9 経由)、Phase 2.5 で「サムネクリック → preview」を追加するかは [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) / [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) で議論。pane の右下に存在した `[境界を調整]` ボタンは [#464](https://github.com/Idios/kobutachan-allaganeye/issues/464) review でトップアクションバーに移動済み (短い viewport で fold 下に隠れるため) |

#### §2.3.11 emptyNote

| 項目 | 内容 |
| --- | --- |
| 種類 | display ([CompleteScreen.tsx:44-50](../gui/src/screens/CompleteScreen.tsx#L44)) |
| 状態 | `complete_empty` のみ表示 (`metadata === null`)。`loadErrorState === null` 時は文言 `'No metadata. Run detect first.'`、`loadErrorState !== null` 時は `role="alert"` で load 失敗の message + hint を表示 ([#814](https://github.com/Idios/kobutachan-allaganeye/issues/814)、`data-testid="complete-load-error"`) |
| 遷移トリガー | `metadata` が null になった瞬間 (clear / 起動直後 / load 失敗後) |
| store mutation | なし |
| 例外 / edge case | 通常フロー (drop → detecting → complete) では到達しない (detecting 完了で `loadSample()` が必ず呼ばれる)。dev 用 StateSwitcher で複数 screen を試行する場合や、Phase 2.5 で `clear()` 経由で意図的に表示する経路が増えた場合の文言 / アクションリンク ([参照…] への戻り) は [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) で議論。[#814](https://github.com/Idios/kobutachan-allaganeye/issues/814): detect 完了後の load 失敗は DetectingScreen が専用 error view (§2.2 detecting error) へルーティングするため通常はそちらで表示されるが、restore reload 失敗等で complete に load 失敗状態が残る経路の保険として本 emptyNote も `loadErrorState` を表示する (P2-13 連鎖の二重防御) |

### §2.4 preview

**phase**: 専用 reducer なし。便宜上の状態名 ([ui-architecture.md](ui-architecture.md) §preview の mermaid に対応):

- `preview_empty` — `match` が見つからない (`emptyNote` 表示)
- `preview_idle` — match あり、操作待機
- `preview_applying` — `metadataStore.applying=true` ([適用] in-flight)
- `preview_applyError` — `metadataStore.applyError !== null`
- `preview_restoring` — `metadataStore.restoring=true` (RestoreButton in-flight)

これらは `metadataStore` のフィールド合成で表現され、追加 reducer は持たない。

**[ui-architecture.md](ui-architecture.md) §preview mermaid との対応**:

- mermaid 図 ([ui-architecture.md](ui-architecture.md) §preview) は画面レベルの遷移を `preview_idle / preview_applying / preview_applyError / preview_restoring / preview_restoreError` の 5 状態で記述する
- 本節は **(差異 1)** `preview_empty` を画面 entry 時の特殊状態として明示 (mermaid では entry 経路として暗黙、§2.4.15 emptyNote と対応)
- **(差異 2)** `preview_restoreError` を §2.4 ヘッダから除外 (RestoreButton 共通 component 内のエラー表示として §2.3.4 / §2.4.13 で扱う。§2.4 ヘッダは preview 画面レベル状態のみ列挙)
- 両者は意図的な分担であり矛盾ではない。後続 §3 (相互リンク + クロスリファレンス) で全画面の状態名と mermaid の対応関係を一括整理する

**editing**: 編集対象パネルを示す local state `editing: 'start' | 'end'` ([PreviewScreen.tsx:101](../gui/src/screens/PreviewScreen.tsx#L101))。`editing` で `currentT` / `setCurrentT` / `activeVideoRef` が分岐し、stepRow / keyboard / FrameStrip の操作対象を決める。`editing` は phase とは独立で、画面マウント中は常に `'start' | 'end'` のいずれか。

**store**: 読み書きは `metadataStore` の `metadata`, `dirty`, `applying`, `applyError`, `filePath`, `updateMatch`, `apply`, `discardEdits` と `appStateStore` の `selectedMatchIndex`, `navigate`, `selectedVideoPath`。書き込み経路は `updateMatch` (matchName / startT / endT は debounce 200ms で coalesce、matchType は §1.1 例外で即時 commit) / `apply` ([適用]) / `discardEdits` (back / export confirm OK で最後の persisted 状態へ revert) / `RestoreButton.restore` (§2.4.13) / `navigate` (back / export / RestoreButton 成功) のみ。

**dirty / silent loss**: §1.3 に従い `handleBack` / `handleExport` が `if (dirty) confirm(...)` → OK で `discardEdits()` 後 `navigate(...)` を実装 ([PreviewScreen.tsx:460-486](../gui/src/screens/PreviewScreen.tsx#L460))。各 input は §1.1 準拠で onChange → debounce 200ms → `updateMatch` → store dirty 即時反映。confirm 直前に `flushUpdate()` でタイマー残を即時 commit するため、`useMetadataStore.getState().dirty` の判定が常に最新の編集を反映する (#589 で確立)。

**sample mode**: `metadataStore.filePath === null` で sample 扱い。[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で全面 read-only 化を実装: 編集 input (matchName / matchType / startT / endT / TC) はすべて disabled、[適用] は `applying → isSample → !filePath` の priority 順で disabled + inline hint 「サンプル動画では保存できません」、上部に `SampleModeBanner` を常時表示。サンプル状態で `discardEdits()` を辿った場合は `loadSample()` で fixture に戻す (#589 で実装済)。

**エラー表示**: §1.5 inline + toast 併用。preview 画面の主要エラー源:

- `applyError` → inline `role="alert"` 表示済み ([PreviewScreen.tsx:660-662](../gui/src/screens/PreviewScreen.tsx#L660))
- `restoreError` → RestoreButton 内 inline `role="alert"` 表示済み (§2.3.4 と共通)
- `videoError` (register_video 失敗) → Pane 内 inline `role="alert"` 表示済み ([PreviewScreen.tsx:750](../gui/src/screens/PreviewScreen.tsx#L750))

global toast への昇格は Phase 2.5 / [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) で complete 画面と統一する。

**実装段階**:

- 現状 (Phase 3 = [#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) + [#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) 完了): `<video>` + axum 配信、`requestVideoFrameCallback` ベースのフレームシーク、ffmpeg サムネキャッシュ、キーボードショートカット ←→ 1s / Shift 10s / Alt 1F / Space 再生、TC HH:MM:SS.FF 入力、frame-grid snap、source_fps 連動 (60/120/240)、§1.1 / §1.3 準拠の state mutation flow + dirty consume confirm が完成
- [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で §1.4 sample mode 全面 read-only (上部 `SampleModeBanner` + 編集 input disabled + 主要 CTA disabled + inline hint) を全画面 (complete §2.3 + preview §2.4 + export §2.5) 一括実装済。§1.2 準拠の disabled 理由表示も各部品節に記載のとおり実装済
- ffmpeg 中断保護 ([#523](https://github.com/Idios/kobutachan-allaganeye/issues/523)): preview では subprocess を持たない (axum 直接配信、サムネは短命) ため、本画面は対象外

#### §2.4.1 [◀ 一覧へ] back button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([PreviewScreen.tsx:496](../gui/src/screens/PreviewScreen.tsx#L496)) |
| 状態 | `idle` (常時活性) |
| 遷移トリガー | `onClick` → `handleBack()` ([PreviewScreen.tsx:460-474](../gui/src/screens/PreviewScreen.tsx#L460)) → `flushUpdate()` で debounce 残を即時 commit → `if (useMetadataStore.getState().dirty) confirm('未保存の変更があります。破棄して一覧へ戻りますか？')` → OK で `discardEdits()` 後 `navigate('complete')`、cancel で preview 残留 |
| store mutation | confirm OK 経路では `metadataStore.metadata` (load 経由で persisted 状態へ revert)、`metadataStore.dirty=false`、`metadataStore.draft.json` clear、`appStateStore.screen='complete'` (discardEdits 完了後)。dirty=false 経路は `appStateStore.screen='complete'` のみ |
| 例外 / edge case | sample mode (filePath==null) では `discardEdits` が `loadSample()` 経路で fixture に戻す (load 経由ではない)。confirm cancel 時は flush だけ走り、編集は store に残ったまま (dirty=true 維持)。文言は §1.3 canonical に統一済 (#589) |

#### §2.4.2 match name input

| 項目 | 内容 |
| --- | --- |
| 種類 | text input ([PreviewScreen.tsx:505](../gui/src/screens/PreviewScreen.tsx#L505)) |
| 状態 | `idle` / `disabled` (sample mode: `isSample=true` で disabled + tooltip 理由「サンプル動画では保存できません」、[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で実装済 → §1.4) |
| 遷移トリガー | `onChange` → local `setMatchName(value)` → schedule effect が pendingPatchRef に `{ name }` を merge → 200ms 後に `updateMatch(match.index, pendingPatch)` を 1 回 commit (§1.1 準拠、debounce で連打を coalesce) |
| store mutation | debounce 完了時 `metadataStore.metadata.matches[i].name`、`metadataStore.dirty=true`、`metadataStore.draft.json` (#517 auto-save、別 debounce 500ms) |
| 例外 / edge case | `name` は metadata.json には書き戻されず GUI 表示専用 ([metadata-spec.md](metadata-spec.md))、placeholder は `match_NNN` フォールバック。空文字許容 (placeholder 表示)。`flushUpdate()` (handleApply / handleBack / handleExport / unmount) で残タイマーを即時実行。`post_match: true` の match を編集中は nameRow 右端に badge「試合後」(`data-testid="post-match-badge"`) を表示する ([#805](https://github.com/Idios/kobutachan-allaganeye/issues/805) Phase 2、表示専用) |

#### §2.4.3 type select

| 項目 | 内容 |
| --- | --- |
| 種類 | `<select>` ([PreviewScreen.tsx:518](../gui/src/screens/PreviewScreen.tsx#L518))。option: `fl_match` / `unknown` / `skip` |
| 状態 | `idle` / `disabled` (sample mode: `isSample=true` で disabled + tooltip 理由「サンプル動画では保存できません」、[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で実装済 → §1.4) |
| 遷移トリガー | `onChange` → local `setMatchType(value)` + `flushUpdate()` で先行 debounce を flush + `updateMatch(match.index, { type_override: value })` を **即時 commit** (§1.1 例外、単一選択型は debounce しない) |
| store mutation | 即時 `metadataStore.metadata.matches[i].type_override`、`metadataStore.dirty=true`、`metadataStore.draft.json` (#517 auto-save 500ms debounce) |
| 例外 / edge case | `skip` は normalizeForPersistence で metadata.json に書き戻されない GUI ローカル情報 ([metadata-spec.md](metadata-spec.md) 編集契約)。即時 commit のためタイピング途中の中間状態は持たず、ユーザーが選んだ瞬間に dirty バッジが点く |

#### §2.4.4 Pane button (activate IN / OUT)

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([PreviewScreen.tsx:682](../gui/src/screens/PreviewScreen.tsx#L682))。IN (start) / OUT (end) の 2 個。`aria-pressed={active}` |
| 状態 | `inactive` / `active` (`editing === 'start'` で IN、`'end'` で OUT) |
| 遷移トリガー | `onClick` → `props.onActivate()` → `setEditing('start' \| 'end')` |
| store mutation | なし (local state) |
| 例外 / edge case | inactive Pane の video / tcInput クリックは `onActivate()` を呼んだ後に play/pause / TC 編集に進む 2 段経路 (§2.4.5 / §2.4.6 で詳述)。`active` 切替で `currentT` / `setCurrentT` / `activeVideoRef` の参照が IN/OUT 間で切り替わる |

#### §2.4.5 Pane.video (`<video>`)

| 項目 | 内容 |
| --- | --- |
| 種類 | `<video>` ([PreviewScreen.tsx:710-748](../gui/src/screens/PreviewScreen.tsx#L710))。axum 配信 URL を `src` に持つ HTML5 player、`controls={false}` |
| 状態 | `loading` (videoUrl null && videoError null → `loading video…` 表示) / `error` (videoError あり → inline `role="alert"`) / `paused` (default、currentTime ↔ startT/endT 双方向同期) / `playing` (`onTimeUpdate` で startT/endT を currentTime に追従) |
| 遷移トリガー | `onClick` → stopPropagation。inactive なら `onActivate()` のみ、active なら `play()` / `pause()` toggle。`onTimeUpdate` (playing 時のみ) → `onTChange(v.currentTime)` で local state に sync |
| store mutation | なし。local state `setStartT` / `setEndT` を介して TC を更新 (debounce 経由で 200ms 後に store dirty へ反映、§2.4.6 と同じ機構) |
| 例外 / edge case | paused 中のみ state→video の seek effect ([PreviewScreen.tsx:279-309](../gui/src/screens/PreviewScreen.tsx#L279))。`v.paused` guard なしだと再生中の onTimeUpdate → setStartT → effect → backward seek の loop で再生がガタつく。Space キーでも再生 / 停止可 (global keyboard handler、§2.4.7 注記)。loading / error 時は `<video>` 自体が render されないため click / keyboard はパススルー |

#### §2.4.6 Pane.tcInput (TC manual entry)

| 項目 | 内容 |
| --- | --- |
| 種類 | text input ([PreviewScreen.tsx:758](../gui/src/screens/PreviewScreen.tsx#L758))。`H:MM:SS.FF` 形式 (FF は frame portion、`source_fps` 連動) |
| 状態 | `idle` / `disabled` (sample mode: `isSample=true` で disabled + tooltip 理由「サンプル動画では保存できません」、[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で実装済 → §1.4) |
| 遷移トリガー | `onChange` → `parseTimecode(value, fps)` → 解析成功時 `onTChange(parsed)` (= local `setStartT` / `setEndT`) → schedule effect が pendingPatchRef に `{ edited: { start_time, end_time } }` を merge → 200ms 後に `updateMatch` を 1 回 commit (§1.1 準拠)。`onClick` → stopPropagation で Pane の activate を抑止 |
| store mutation | debounce 完了時 `metadataStore.metadata.matches[i].edited.start_time/end_time`、`dirty=true`、`draft.json` (#517 別 debounce 500ms) |
| 例外 / edge case | `parseTimecode` が null を返す (malformed input) 場合は何もしない (input value は ユーザー編集中の状態を維持)。表示は `fmtPreciseTime(t, fps)` で常に正規化された TC を出すため、playback 中はフレーム単位で値が動く。frame portion は `parseInt(f, 10) / fps` で 60/120/240 fps に対応 |

#### §2.4.7 stepRow buttons (×6)

| 項目 | 内容 |
| --- | --- |
| 種類 | button × 6 ([PreviewScreen.tsx:594-617](../gui/src/screens/PreviewScreen.tsx#L594))。`-10s / -1s / -1F / +1F / +1s / +10s`。`title="<label> (<key hint>)"` で keyboard 等価操作明示、`aria-label="nudge <label>"` |
| 状態 | `idle` / `disabled` (sample mode: `isSample=true` で disabled + tooltip 理由「サンプル動画では保存できません」、[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で実装済 → §1.4) |
| 遷移トリガー | `onClick` → frame ボタンは `nudgeFrame(±1)` (frame-grid snap)、秒 ボタンは `nudge(±1 \| ±10)` (累積) → 内部で `setCurrentT(...)` → schedule effect 経由で 200ms 後に `updateMatch({ edited })` commit |
| store mutation | debounce 完了時 `metadataStore.metadata.matches[i].edited.start_time/end_time`、`dirty=true` |
| 例外 / edge case | global keyboard ([PreviewScreen.tsx:407-436](../gui/src/screens/PreviewScreen.tsx#L407)) が ←/→/Shift+←→/Alt+←→ に同等の `nudge` / `nudgeFrame` を割り当てる。INPUT/TEXTAREA/SELECT に focus 中はキーボードを `return` で吸わない (TC input への入力を妨げない)。frame-grid snap は IEEE 754 丸め誤差で `t + 1/fps` の frame portion が advance しないケースを回避するため frame 番号ベースで step (例: 2438.75 + 1/120 → frame .90 のままバグ) |

#### §2.4.8 keyHint display

| 項目 | 内容 |
| --- | --- |
| 種類 | display block ([PreviewScreen.tsx:621-635](../gui/src/screens/PreviewScreen.tsx#L621))。`role="note"` + `aria-label="keyboard shortcuts"`、`<kbd>` で各キー表示 |
| 状態 | `displayOnly` |
| 遷移トリガー | なし (常時可視) |
| store mutation | なし |
| 例外 / edge case | stepRow / global keyboard handler の操作可能性を初学者にも提示する役割。Phase 2.5 で `←/→ ⌥ Shift Space` を OS (mac/win) 別表記に切り替えるかは [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) a11y/polish で議論 |

#### §2.4.9 FrameStrip

| 項目 | 内容 |
| --- | --- |
| 種類 | sub-component ([PreviewScreen.tsx:638-647](../gui/src/screens/PreviewScreen.tsx#L638))。±3s 範囲、12 frames @ 0.5s 間隔、現境界中心の thumb 列 + #645 で **brightness overlay** (SVG semi-transparent、`pointer-events: none` で thumbnail click を阻害しない) を追加 |
| 状態 | `displayOnly` (frame の sample) + interactive (frame click)。`brightness overlay` は thumb 上に半透明 SVG layer を重ねる: 輝度波形 (gold) / 閾値線 (red dashed) / blackout band (cyan)。 sample mode: thumb click は no-op (isSample=true で `onSelectFrame` を呼ばない、[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) → §1.4)。brightness data は currentT ±3s で `extract_brightness_window` invoke (200ms debounce、currentT 変動に追従) |
| 遷移トリガー | thumb `onClick` → `props.onSelectFrame(t)` → `setCurrentT(t)` → schedule effect 経由で 200ms 後に `updateMatch({ edited })` commit。brightness fetch は currentT / videoSource / isSample / match.index 変更で再発火 (200ms debounce) |
| store mutation | debounce 完了時 `metadataStore.metadata.matches[i].edited.start_time/end_time`、`dirty=true`。brightness overlay は store mutation なし (PreviewScreen 内 local state、`brightnessWindow` / `overlayError`) |
| 例外 / edge case | `editing` で `inThumbs` / `outThumbs` を切替表示。thumbs の生成は ffmpeg `generate_match_thumbnails` (Rust 経由) で、boundary が 0.5s 以上動いた時のみ再フェッチ。失敗時は空配列 (UI は空 strip 表示)、エラー文言は出さない (#465 設計判断)。brightness overlay は data なし or fetch 失敗時に SVG 自体が render されない (back-compat、優雅な degrade); fetch 失敗時は inline 診断メッセージを strip 直下に表示 (`toErrorState(e)` → `overlayState.message` + `<InlineErrorHint hint={overlayState.hint} />`)。sample mode (`filePath===null`) は invoke せず `buildLocalBrightness(currentT, 3, 10).map(s => s.b)` で synthetic 波形 |

#### §2.4.10 [適用] primary button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([PreviewScreen.tsx:651-657](../gui/src/screens/PreviewScreen.tsx#L651))。`aria-label="apply"` |
| 状態 | `idle` (`!applying && !isSample && filePath !== null && boundaryValid`) / `applying` (label = `'適用中…'`) / `disabled` (priority: `applying` → `isSample` → `!filePath` → `!boundaryValid` (`end <= start`)) |
| 遷移トリガー | `onClick` → `handleApply()` ([PreviewScreen.tsx:451-457](../gui/src/screens/PreviewScreen.tsx#L451)) → `flushUpdate()` で残 debounce を即時 commit → `filePath` がある場合のみ `apply()` を await。debounce 経路で既に store の dirty 編集が立っている前提で、handleApply は二重 commit を行わない (§1.1 #589 修正で確立) |
| store mutation | `metadataStore.applying`、`metadataStore.applyError`、`metadataStore.loadedMtimeMs` (apply 成功時)、`metadataStore.dirty=false` (apply 完了)、`metadataStore.hasBackup` (`refreshBackupStatus`)、`metadataStore.metadata.draft.json` clear ([#517](https://github.com/Idios/kobutachan-allaganeye/issues/517) draft auto-save 連携)。matches 編集自体は debounce 経路で既に commit 済 |
| 例外 / edge case | sample mode (`isSample=true`) では disabled + tooltip 「サンプル動画では保存できません」 + inline hint を同時表示 ([#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で §1.2 準拠実装済)。conflict 時は ConflictModal ([metadata-spec.md](metadata-spec.md) §排他管理) が global で表示される (本画面では特段の追加処理なし)。[#814](https://github.com/Idios/kobutachan-allaganeye/issues/814): `boundaryValid = isBoundaryValid(startT, endT)` (`end > start`) でない時も disabled + inline hint「終了 (OUT) は開始 (IN) より後にしてください」。境界編集 (nudge / frame step / FrameStrip / TC 入力 / playback) は `commitStart` / `commitEnd` で相互クランプし `startT < endT (1 フレーム以上の gap)` を維持、`apply()` は store `runApply` が apply 直前に全 match の `end > start` を強制し違反時は `apply_changes` を invoke せず `applyErrorState` (code `validation.boundary_invalid`) を set、Rust `apply_changes_sync` も同 guard を持つ多層防御 (read は zod `end >= start` で寛容、write は厳格で OUT<IN による metadata.json 破損 = P1-2 を防ぐ) |

#### §2.4.11 dirty indicator

| 項目 | 内容 |
| --- | --- |
| 種類 | display badge ([PreviewScreen.tsx:658](../gui/src/screens/PreviewScreen.tsx#L658))。`● 未保存の変更` 文言 |
| 状態 | `displayOnly`。`dirty=true` のみ render |
| 遷移トリガー | `metadataStore.dirty` 変化に追従 |
| store mutation | なし |
| 例外 / edge case | §1.1 準拠の debounce で onChange の ~200ms 後 (matchType は即時) に dirty=true へ flip し、編集中バッジが表示される (#589 修正で実現)。apply 完了で false に戻る |

#### §2.4.12 applyError inline

| 項目 | 内容 |
| --- | --- |
| 種類 | inline error ([PreviewScreen.tsx:660-662](../gui/src/screens/PreviewScreen.tsx#L660))。`role="alert"` |
| 状態 | `displayOnly`。`applyError !== null` のみ render |
| 遷移トリガー | `metadataStore.applyError` 変化に追従 (apply 失敗で set、次の apply 試行で clear) |
| store mutation | なし |
| 例外 / edge case | dismiss UI 未実装 (再 apply で消える設計)、conflict は別経路 (ConflictModal) のため本 inline には出ない。Phase 2.5 で global toast への昇格 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569))、文言の §1.5 行動指針化 (canonical: 「保存に失敗しました。<原因>。<次の行動>」) を実装 |

#### §2.4.13 [元に戻す] (RestoreButton)

| 項目 | 内容 |
| --- | --- |
| 種類 | RestoreButton 共通 component ([PreviewScreen.tsx:665](../gui/src/screens/PreviewScreen.tsx#L665))。`onRestored={() => navigate('complete')}` で復元成功後に complete へ戻る |
| 状態 | §2.3.4 と共通 (`idle` / `busy` / `disabled`) |
| 遷移トリガー | confirm → `restore()` → 成功で `onRestored` callback → `navigate('complete')` |
| store mutation | §2.3.4 と共通。preview 画面では navigate('complete') が追加発火 |
| 例外 / edge case | restore はディスク上の `metadata.json` を上書きするため、画面遷移を伴わずに preview に留まると編集中の local state (startT / endT 等) が新しい match と矛盾する。これを回避するため preview からは `onRestored` で必ず complete に戻す設計 (§2.3.4 では callback 未指定で同画面に留まる)。§1.2 disabled 理由 tooltip / inline hint (priority: `restoring` → `isSample` → `!hasBackup`) は §2.3.4 と共通の実装で [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) 対応済 |

#### §2.4.14 [書き出し] secondary button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([PreviewScreen.tsx:667-672](../gui/src/screens/PreviewScreen.tsx#L667)) |
| 状態 | `idle` (常時活性) |
| 遷移トリガー | `onClick` → `handleExport()` ([PreviewScreen.tsx:476-486](../gui/src/screens/PreviewScreen.tsx#L476)) → `flushUpdate()` で debounce 残を即時 commit → `if (useMetadataStore.getState().dirty) confirm('未保存の変更があります。破棄して書き出しへ進みますか？')` → OK で `discardEdits()` 後 `navigate('export')`、cancel で preview 残留 |
| store mutation | confirm OK 経路では §2.4.1 と同じく load 経由 revert + dirty=false + draft clear、`appStateStore.screen='export'` (discardEdits 完了後)。dirty=false 経路は `appStateStore.screen='export'` のみ |
| 例外 / edge case | §2.4.1 と同形状 (sample mode discardEdits は loadSample 経路 / cancel で flush のみ + dirty 維持)。文言は §1.3 canonical 統一済 (#589) |

#### §2.4.15 emptyNote

| 項目 | 内容 |
| --- | --- |
| 種類 | display ([PreviewScreen.tsx:443-449](../gui/src/screens/PreviewScreen.tsx#L443))。文言: `'No match selected.'` |
| 状態 | `preview_empty` のみ表示 (`match` が見つからない、つまり `selectedMatchIndex` が `metadata.matches` のどれとも一致しない) |
| 遷移トリガー | `selectedMatchIndex` または `metadata.matches` 変化で `match` が解決できなくなった時 |
| store mutation | なし |
| 例外 / edge case | 通常フロー (complete から double-click / [境界を調整]) では到達しない。dev StateSwitcher で preview に直接遷移したり、apply 後 matches 配列が変動して selectedMatchIndex が消えた場合に表示。文言と「complete へ戻る」リンクは [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) a11y/polish で議論 |

#### §2.4.16 header path display (#676)

| 項目 | 内容 |
| --- | --- |
| 種類 | display block ([PreviewScreen.tsx:629](../gui/src/screens/PreviewScreen.tsx#L629) `.headerInfo` 内、`.caption` の上に配置) |
| 状態 | `displayOnly`。`videoSource` 不在 (sample mode 等で `selectedVideoPath` も `metadata.source` も null) のとき非 render |
| 遷移トリガー | `videoSource` (= `selectedVideoPath ?? metadata?.source ?? null`) 変化に追従 |
| store mutation | なし |
| 例外 / edge case | **§1.6 ファイルパス表示の原則に準拠** — `videoSource` を `splitPath()` で分解、primary `.headerFileName` (13px / text-bright、PreviewScreen.module.css 新設) + secondary `.pathSecondary` (parentDir 左側省略) + container `title={videoSource}` (`data-testid="preview-path"`、#676)。`videoSource === null` で領域全体を非表示 (条件付き render) |

### §2.5 export

**phase**: 専用 reducer ([reducers/export.ts:19-48](../gui/src/screens/reducers/export.ts#L19))。`idle | running | cancelling | completed | error`

- `idle` → `running` (`START_CLICKED`)
- `running` → `cancelling` (`CANCEL_CLICKED`) / `completed` (`PROGRESS_COMPLETE`) / `error` (`EXPORT_ERROR`)
- `cancelling` → `completed` (`PROGRESS_COMPLETE`、中断要求後に export が中断前に完了した race、[#837](https://github.com/Idios/kobutachan-allaganeye/issues/837)) / `idle` (`CANCEL_CONFIRMED` または `EXPORT_ERROR`)
- `completed` → `idle` (`RESTART`)
- `error` → `idle` (`DISMISS_ERROR` / `RESTART`)

**[ui-architecture.md](ui-architecture.md) §export mermaid との対応**:

- mermaid 図は `export_idle / export_running / export_cancelling / export_completed / export_error` の 5 状態。本節は接頭辞 `export_` を省略した内部 reducer 名に揃えている (実装では `phase: ExportPhase` 直値を使う)
- mermaid の `export_cancelling` 状態は ffmpeg 停止後 `export_idle` に直結する (`export_cancelling → export_idle: ffmpeg 停止`) ほか、中断要求が export 完了を追い越した race では `export_cancelling → export_completed: PROGRESS_COMPLETE` に遷移する (#837 / P2-14)。終端の `cancelled` 状態は持たない。内部 reducer の `cancelling → idle (CANCEL_CONFIRMED)` / `cancelling → completed (PROGRESS_COMPLETE)` と同形状で整合する。後続 §3 で全画面分の整理を行う

**store**: 主に **読み取り** (`metadataStore.metadata`、`appStateStore.selectedVideoPath`)。書き込みは `appStateStore.navigate('preview')` ([◀ プレビュー]) のみ。export 自体は store ではなく **Tauri command `start_export`** (単発 invoke → Python pool が N 並列 ffmpeg を spawn) + **event `export-progress`** + local state (`matchStates` / `excludedIndexes` / `outDir` / `namePattern` / `codec` / `encoderSlots` / `encoderBadge` 等) で駆動する。

**dirty / silent loss**: 編集対象 metadata なしのため §1.3 silent loss 対象外。export screen 上の設定 (`outDir` / `namePattern` / `codec` / `excludedIndexes`) は session-local config 扱いで confirm 不要。`running / cancelling` 中は [◀ プレビュー] が disabled になり物理的に navigate を防ぐ。

**sample mode**: §1.4 通り。[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で export 画面にも `SampleModeBanner` を追加し、export 設定入力 (出力先 / 命名規則 / コーデック) と [書き出し開始] を sample mode で disabled にして read-only 化済。`metadata.source` がフォールバックで `videoSource !== null` になってしまう経路も sample mode disabled で遮断される。

**エラー表示**: §1.5 inline 中心。export 画面の主要エラー源:

- `errorMessage` (phase=`error`、全試合 fail) → inline `role="alert"` ([ExportScreen.tsx:533-537](../gui/src/screens/ExportScreen.tsx#L533))
- per-match `s.error` → listItem 内 inline `role="alert"` ([ExportScreen.tsx:759-763](../gui/src/screens/ExportScreen.tsx#L759)、120 文字 slice)
- per-match `s.fallbackNotice` (#591 GPU encoder fallback 通知) → listItem 内 `role="status"` ([ExportScreen.tsx:764-773](../gui/src/screens/ExportScreen.tsx#L764)、エラーではなく info)
- `openFolderError` ([フォルダを開く] 失敗) → primary button 直下に inline `role="alert"` ([ExportScreen.tsx:618-622](../gui/src/screens/ExportScreen.tsx#L618))

global toast 未採用 (画面が log 中心で各情報源と表示位置が固定されているため、inline 集約で十分)。Phase 2.5 / [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) で他画面と統一した toast 方針が決まればそれに合わせる。

**実装段階**:

- 現状 (Phase 4 = [#466](https://github.com/Idios/kobutachan-allaganeye/issues/466) / [#545](https://github.com/Idios/kobutachan-allaganeye/pull/545) / [#591](https://github.com/Idios/kobutachan-allaganeye/issues/591) 完了): 実 ffmpeg 呼び出し + per-match progress event + GPU encoder auto-select + libx264 fallback + cancel kill ([#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) と共通の `kill_tracked_processes`) + `open_folder_in_explorer` (shell.open scope 制約回避) + `{start}` filename 用 MM-SS 表記 + 経過 / 残り時間表示 + 全選択 / 全解除 + per-match exclude
- [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633): §1.4 sample mode `SampleModeBanner` + 8 disabled CTA の read-only 化 + §1.2 準拠 disabled 理由 tooltip を実装済。各部品節を参照

#### §2.5.1 [◀ プレビュー] back button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([ExportScreen.tsx:458-465](../gui/src/screens/ExportScreen.tsx#L458)) |
| 状態 | `idle` / `disabled` (`running \|\| cancelling`) |
| 遷移トリガー | `onClick` → `navigate('preview')` |
| store mutation | `appStateStore.screen='preview'` |
| 例外 / edge case | running / cancelling 中の navigate を物理的に防ぐ (kill_tracked_processes が必要、§2.5.10 [中断] 経由でないと安全に止まれない)。§1.2 disabled 理由 tooltip「書き出し中はプレビューに戻れません。先に [中断] してください」 ([#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で実装済) |

#### §2.5.2 header (caption + title)

| 項目 | 内容 |
| --- | --- |
| 種類 | display block ([ExportScreen.tsx:466-471](../gui/src/screens/ExportScreen.tsx#L466))。caption "エクスポート" + title "{N} 試合を書き出す" |
| 状態 | `displayOnly`。`countedMatches.length` (永続 skip + ad-hoc exclude を除外した数) を反映 |
| 遷移トリガー | `metadata.matches` / `excludedIndexes` 変化に追従 |
| store mutation | なし |
| 例外 / edge case | `countedMatches.length === 0` のとき "0 試合を書き出す" 表示で無意味だが、画面全体としては start ボタン disabled (`!videoSource`) で実害なし。0 件時の専用文言 + start 無効化は [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) 議論対象。**§1.6 ファイルパス表示の原則に準拠** — header caption/title の上に `videoSource` 由来の 2 段 path display を render (primary `.headerFileName` (13px) + secondary `.pathSecondary` 左側省略 + container `title={videoSource}`、`data-testid="export-path"`、#676)。`videoSource === null` で領域全体を非表示 |

#### §2.5.3 出力先 input

| 項目 | 内容 |
| --- | --- |
| 種類 | text input ([ExportScreen.tsx:481-487](../gui/src/screens/ExportScreen.tsx#L481))。`aria-label="output directory"` |
| 状態 | `idle` / `disabled` (`running \|\| cancelling \|\| isSample`。sample mode disabled + tooltip 理由「サンプル動画では保存できません」、[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) → §1.4) |
| 遷移トリガー | `onChange` → 即時 `setOutDir(value)` (local state) |
| store mutation | なし (session-local config、§1.1 例外: metadata 編集ではない設定値は store に上げない) |
| 例外 / edge case | default 値は `deriveDefaultOutDir(videoSource)` ([ExportScreen.tsx:122](../gui/src/screens/ExportScreen.tsx#L122)、`<dirname(videoSource)>/output`)。videoSource 欠損時は空文字列で必須選択。Windows extended-length path prefix (`\\?\`) は `stripExtendedPathPrefix` で除去。親ディレクトリが存在しない場合は Rust 側で error (silent mkdir は廃止) |

#### §2.5.4 [参照…] dir picker button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([ExportScreen.tsx:488-495](../gui/src/screens/ExportScreen.tsx#L488)) |
| 状態 | `idle` / `disabled` (`running \|\| cancelling`) |
| 遷移トリガー | `onClick` → `openDialog({ directory: true, multiple: false })` (`@tauri-apps/plugin-dialog`) → 戻り値 string なら `setOutDir(picked)` |
| store mutation | なし |
| 例外 / edge case | `dialog:allow-open` permission を `capabilities/default.json` に明示済み。dialog cancel (戻り値 null) は何もしない。§1.2 disabled 理由 tooltip (「書き出し中は変更できません」/ sample: 「サンプル動画では保存できません」) [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で実装済 |

#### §2.5.5 命名規則 input + variables hint

| 項目 | 内容 |
| --- | --- |
| 種類 | text input + display hint ([ExportScreen.tsx:501-510](../gui/src/screens/ExportScreen.tsx#L501))。default `match_{idx:03}.mp4` |
| 状態 | input: `idle` / `disabled` (`running \|\| cancelling \|\| isSample`。sample mode disabled + tooltip 理由「サンプル動画では保存できません」、[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) → §1.4)。hint: `displayOnly` |
| 遷移トリガー | input `onChange` → 即時 `setNamePattern(value)` |
| store mutation | なし (session-local) |
| 例外 / edge case | `formatName` で `{idx}` / `{idx:03}` / `{type}` / `{start}` / `{date}` を置換。`{start}` は `formatStartForFilename` で `MM-SS` / `H-MM-SS` 形式 (Windows filename で `:` 不可のため `-` 置換)。malformed pattern (置換キーなし等) は実体ファイル名がそのまま出るのみで error にしない。重複ファイル名は ffmpeg `-y` で silent overwrite |

#### §2.5.6 コーデック selector (copy / h264 buttons)

| 項目 | 内容 |
| --- | --- |
| 種類 | button × 2 ([ExportScreen.tsx:516-528](../gui/src/screens/ExportScreen.tsx#L516))。`aria-pressed={codec === c.v}` で選択状態を提示 |
| 状態 | 各ボタン: `inactive` / `active` (`codec === c.v` で `codecButtonActive`) / `disabled` (`running \|\| cancelling \|\| isSample`。sample mode disabled + tooltip 理由「サンプル動画では保存できません」、[#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) → §1.4) |
| 遷移トリガー | `onClick` → 即時 `setCodec(value)` |
| store mutation | なし |
| 例外 / edge case | h264 ボタンの sub label に `encoderBadge` を埋め込み、auto-select 結果 (`NVENC ×N` / `QSV` / `AMF` / `libx264 (CPU)`) を可視化 ([#761](https://github.com/Idios/kobutachan-allaganeye/issues/761))。`metadata.system_info` 欠損 / Tauri command reject 時は libx264 silent fallback。codec 未選択状態は無し (default `'copy'`) |

#### §2.5.7 errorMessage (phase=error)

| 項目 | 内容 |
| --- | --- |
| 種類 | inline alert ([ExportScreen.tsx:533-537](../gui/src/screens/ExportScreen.tsx#L533))。`role="alert"`、文言: `すべての試合の書き出しが失敗しました` |
| 状態 | `displayOnly`。`phase === 'error'` のみ表示 (= `successCount === 0 && failureCount > 0`) |
| 遷移トリガー | reducer `EXPORT_ERROR` 遷移時に表示開始、`DISMISS_ERROR` / `RESTART` で消える |
| store mutation | なし |
| 例外 / edge case | per-match の個別 error は §2.5.15 listItem 側で `s.error` が表示されるため、本 alert は overall failure のサマリ役。`successCount > 0` なら `completed` phase に遷移し本 alert は出ない (per-match error を listItem で確認させる設計) |

#### §2.5.8 progressBox (label + counts + percent + bar + time)

| 項目 | 内容 |
| --- | --- |
| 種類 | composite display ([ExportScreen.tsx:538-578](../gui/src/screens/ExportScreen.tsx#L538))。label / counts / overallPercent / progressBar / 経過 / 残り |
| 状態 | `displayOnly`。`running \|\| completed \|\| cancelling` のいずれかで表示 |
| 遷移トリガー | reducer phase 変化 / `matchStates` 変化 / 1s tick (`nowMs` 更新) |
| store mutation | なし |
| 例外 / edge case | overallPercent は `(Σ per-match percent) / countedMatches.length` (旧実装の `doneCount / total` 方式は 1 ファイル目 encoding 中 0% 固定問題があり廃止)。残り時間は `(elapsed / progress) * remaining` の線形推定、`progress=0` で `'—'` 表示。完了時 / cancelling 中は `remainingSec=null`。label は `running` / `cancelling` / `completed` で「分割・書き出し中」「中断中…」「完了」と切替 |

#### §2.5.9 [⬦ 書き出し開始] primary button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([ExportScreen.tsx:580-595](../gui/src/screens/ExportScreen.tsx#L580))。`!completed && !error` でのみ render |
| 状態 | `idle` (label `⬦ 書き出し開始`) / `running` (label `書き出し中…`、disabled) / `cancelling` (label `中断中…`、disabled) / `disabled` (`!videoSource`) |
| 遷移トリガー | `onClick` → `handleStartExport()` → `dispatch(START_CLICKED)` (idle→running) → 単発 `invoke('start_export', ...)` → Python subprocess が N 並列 ffmpeg を spawn → 各試合完了ごとに `export-progress` イベントで `PROGRESS_EVENT` dispatch → 全完了で `PROGRESS_COMPLETE` / 全失敗で `EXPORT_ERROR` / cancel で `CANCEL_CONFIRMED` |
| store mutation | なし。`matchStates` / `exportStartMs` / `nowMs` / 内部 phase が更新 |
| 例外 / edge case | `!metadata` または `!videoSource` で early return。永続 skip (`type_override === 'skip'`) または ad-hoc exclude (`excludedIndexes` 含む) は Python 側 `--exclude` で除外。単発 `invoke('start_export', ...)` で Python subprocess を起動、Python pool が N 並列で ffmpeg を spawn。§1.2 disabled 理由: sample mode は「サンプル動画では保存できません」/ `!videoSource` は「動画ファイルが選択されていません。drop 画面に戻って選択してください」/ running / cancelling は当該ボタン非表示で代替。([#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で sample mode 対応実装済) |

#### §2.5.10 [中断] cancel button

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([ExportScreen.tsx:597-605](../gui/src/screens/ExportScreen.tsx#L597))。`running` のみ render |
| 状態 | `idle` (running 中のみ render され activated) |
| 遷移トリガー | `onClick` → `handleCancelClicked()` → `dispatch(CANCEL_CLICKED)` (running→cancelling) + `void invoke('kill_tracked_processes')` |
| store mutation | なし |
| 例外 / edge case | `kill_tracked_processes` は tracked process tree (Python + ffmpeg) を即時 kill (Windows は Job Object hard-kill、[#523](https://github.com/Idios/kobutachan-allaganeye/issues/523))。失敗は silent (`.catch(() => undefined)`)。`start_export` 完了が cancel を追い越した race では `PROGRESS_COMPLETE` で `cancelling → completed` ([#837](https://github.com/Idios/kobutachan-allaganeye/issues/837) / P2-14)、それ以外は `CANCEL_CONFIRMED` → idle 復帰。書き出し済み match は完了状態を保持。**中断時に書き出し中だった partial .mp4 はディスクに残置する** (hard-kill で Python の cleanup が走らないため、#837 / P3-b) |

#### §2.5.11 [✓ 完了 — フォルダを開く] + openFolderError

| 項目 | 内容 |
| --- | --- |
| 種類 | button + inline alert ([ExportScreen.tsx:607-622](../gui/src/screens/ExportScreen.tsx#L607))。`completed` のみ render |
| 状態 | button: `idle` / inline alert: `displayOnly` (`openFolderError !== null` 時のみ) |
| 遷移トリガー | `onClick` → `handleOpenFolder()` → `invoke('open_folder_in_explorer', { path: outDir })` → 失敗時 `setOpenFolderError(message)` |
| store mutation | なし |
| 例外 / edge case | `shell.open` は default scope が URL のみ許可で local path で正規表現 fail するため、Rust 側に専用 command `open_folder_in_explorer` を追加 (#545 review #6)。完了後 navigate しない (旧実装は `navigate('complete')` で Explorer が開く前に画面遷移する不具合あり)。§1.5 文言は技術詳細 (canonical: より行動指針的に「フォルダを開けませんでした: <理由>。手動で `<path>` を開いてください」) |

#### §2.5.12 [設定変更して再書き出し] (completed)

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([ExportScreen.tsx:623-639](../gui/src/screens/ExportScreen.tsx#L623))。`completed` のみ render |
| 状態 | `idle` |
| 遷移トリガー | `onClick` → `setMatchStates({})` + `setOpenFolderError(null)` + `dispatch(RESTART)` (completed→idle) |
| store mutation | なし |
| 例外 / edge case | `outDir` / `namePattern` / `codec` / `excludedIndexes` は保持されるため、ユーザーは画面上で再設定して再実行できる。既存ファイルは ffmpeg `-y` で silent overwrite。tooltip で「同じ metadata を別設定で再書き出し」+「既に同名ファイルがある場合は上書き」を明示 |

#### §2.5.13 [設定変更して再試行] (error)

| 項目 | 内容 |
| --- | --- |
| 種類 | button ([ExportScreen.tsx:641-657](../gui/src/screens/ExportScreen.tsx#L641))。`error` のみ render |
| 状態 | `idle` |
| 遷移トリガー | `onClick` → `setMatchStates({})` + `setOpenFolderError(null)` + `dispatch(DISMISS_ERROR)` (error→idle) |
| store mutation | なし |
| 例外 / edge case | §2.5.12 と同じ semantics (`RESTART` も同じ idle 遷移)。tooltip 文言で「設定を変更してから再度書き出しを試行」を明示 |

#### §2.5.14 listHeader + bulk actions [全選択] / [全解除]

| 項目 | 内容 |
| --- | --- |
| 種類 | display caption + button × 2 ([ExportScreen.tsx:662-689](../gui/src/screens/ExportScreen.tsx#L662)) |
| 状態 | caption: `displayOnly` (`{N} ファイル`)。bulk button: `idle` / `disabled` (`running \|\| cancelling \|\| sample mode \|\| bulk 対象 0 件`) |
| 遷移トリガー | `onClick` → `toggleSelectAll(true \| false)` → `excludedIndexes` から bulk 対象 (永続 skip / `post_match` 以外) を全 add/delete |
| store mutation | なし |
| 例外 / edge case | `type_override === 'skip'` (preview で永続設定) と `post_match: true` ([#805](https://github.com/Idios/kobutachan-allaganeye/issues/805) Phase 2) は bulk 対象外 (個別 checkbox も disabled)。bulk 対象 0 件時 (全 match が永続 skip / post_match) は両 button とも `disabled` + §1.2 理由 tooltip (per-button 文言: 全選択側「対象が 0 件のため全選択できません」/ 全解除側「対象が 0 件のため全解除できません」)。§1.2 disabled 理由 tooltip「書き出し中は変更できません」 ([#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) で実装済) |

#### §2.5.15 listItem (per-match row)

| 項目 | 内容 |
| --- | --- |
| 種類 | composite `<li>` ([ExportScreen.tsx:691-776](../gui/src/screens/ExportScreen.tsx#L691))。checkbox / status mark / name / duration / per-match progress bar / per-match error / fallbackNotice |
| 状態 | checkbox: `checked` (`isIncluded`) / `unchecked` (`isAdHocExcluded`) / `disabled` (`isPersistSkip \|\| isPostMatch \|\| running \|\| cancelling`)。statusMark: `pending(○) / running(●) / done(✓) / error(!) / skipped(—)` (post_match 行は常に `—`)。per-match progress bar: `running \|\| completed \|\| done \|\| error` で表示。post_match 行は `listItemPostMatch` (dimmed) + `data-post-match="true"` + badge「試合後」([#805](https://github.com/Idios/kobutachan-allaganeye/issues/805) Phase 2) |
| 遷移トリガー | checkbox `onChange` → `toggleMatchExclusion(matchIndex)` (`excludedIndexes` add/delete)。Tauri event `export-progress` payload `{match_index, percent, stage, message, fallback_from}` で `matchStates[index]` 更新 |
| store mutation | なし |
| 例外 / edge case | duration 表示は `m.edited` がある場合 `effectiveEnd - effectiveStart` を `fmtMatchDuration` で再計算 (旧実装は CLI 初期値 `m.duration_display` 固定、preview 編集が反映されないバグの修正)。`s.error` は 120 文字で slice (UI が崩れないため)。`fallbackNotice` は GPU encoder fail で libx264 retry した試合に `role="status"` で表示 (エラーではない info、color: `var(--ae-accent)`)。checkbox tooltip で永続 skip (`preview 画面で skip 設定済 (変更不可)`) / post_match (`試合後の映像のため書き出し対象外です`、[#805](https://github.com/Idios/kobutachan-allaganeye/issues/805) Phase 2) / 通常選択 (`書き出し対象から除外/復帰`) を区別。post_match の機能的な export 除外は Phase 1 の `export.py` skip が正で、本行は表示・選択 UX のみ |

#### §2.5.16 emptyNote

| 項目 | 内容 |
| --- | --- |
| 種類 | display ([ExportScreen.tsx:399-405](../gui/src/screens/ExportScreen.tsx#L399))。文言: `'No metadata loaded.'` |
| 状態 | `displayOnly`。`metadata === null` のみ render |
| 遷移トリガー | `metadata` が null になった瞬間 |
| store mutation | なし |
| 例外 / edge case | 通常フロー (complete から [全試合書き出し] / preview から [書き出し →]) では到達しない。dev StateSwitcher 経由のみ表示。文言 / 戻り導線 ([参照…] / drop へ) は [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) a11y/polish で議論 |

## 3. 既存 doc との分担 + クロスリファレンス

### 3.1 doc 分担

| doc | スコープ |
| --- | --- |
| [ui-architecture.md](ui-architecture.md) | screen / phase 2 層 state machine、screen 間遷移、コンポーネント階層、CSS Modules 慣例、性能目標 |
| [design/README.md](design/README.md) | デザインシステム (色 / タイポ)、画面レイアウト原本 (handoff bundle)、各画面の機能仕様 |
| [metadata-spec.md](metadata-spec.md) | metadata.json スキーマ・読み書き契約 (CLI / GUI 共通)・排他管理 ([#514](https://github.com/Idios/kobutachan-allaganeye/issues/514)) ・draft auto-save ([#517](https://github.com/Idios/kobutachan-allaganeye/issues/517)) |
| **本 doc** | **各画面 UI 部品ごとの操作 → store mutation → 例外処理の状態機械 + 共通原則** |

責務の境界:

- **画面間遷移は ui-architecture.md** が source of truth。本 doc は画面間遷移を再記述しない (「→ navigate('complete')」程度の参照のみ)
- **ピクセル / 色 / タイポは design/README.md** が source of truth。本 doc は disabled の見た目等を「`var(--ae-text-dim)` 系」のような token 参照で記述
- **metadata.json の field 仕様は metadata-spec.md** が source of truth。本 doc は store mutation の対象 field を field 名のみで参照

### 3.2 状態名と mermaid 対応表

5 画面の便宜状態名 (§2 各画面ヘッダで定義) と [ui-architecture.md](ui-architecture.md) §各画面 mermaid の状態を対応付ける。差異は意図的な分担 (§3.3 で集約) であり矛盾ではない。

| 画面 | reducer | 本 doc 状態 (§2.x ヘッダ) | mermaid 状態 ([ui-architecture.md](ui-architecture.md)) | 差異 |
| --- | --- | --- | --- | --- |
| drop (§2.1) | あり ([reducers/drop.ts](../gui/src/screens/reducers/drop.ts)) | `idle / selecting / probing / selected / probeError` | `drop_idle / drop_selecting / drop_probing / drop_selected / drop_probeError` | なし (本 doc は接頭辞 `drop_` 省略のみ) |
| detecting (§2.2) | あり ([reducers/detecting.ts](../gui/src/screens/reducers/detecting.ts)) | `running / cancelling / cancelled / completed / error` | `detecting_running / detecting_cancelling / detecting_cancelled / detecting_completed / detecting_error` | なし (本 doc は接頭辞 `detecting_` 省略のみ) |
| complete (§2.3) | なし | `complete_empty / complete_idle / complete_restoring` | `complete_idle / complete_restoring / complete_restoreError` | `complete_empty` は本 doc のみ (entry-time 特殊状態、§2.3.11 emptyNote と対応) / `complete_restoreError` は mermaid のみ (RestoreButton 共通 component 内 inline alert、§2.3.4 で扱う) |
| preview (§2.4) | なし | `preview_empty / preview_idle / preview_applying / preview_applyError / preview_restoring` | `preview_idle / preview_applying / preview_applyError / preview_restoring / preview_restoreError` | `preview_empty` は本 doc のみ (§2.4.15 emptyNote) / `preview_restoreError` は mermaid のみ (§2.4.13 RestoreButton 共通 component) |
| export (§2.5) | あり ([reducers/export.ts](../gui/src/screens/reducers/export.ts)) | `idle / running / cancelling / completed / error` | `export_idle / export_running / export_cancelling / export_completed / export_error` | 本 doc は接頭辞 `export_` 省略 (実装の `phase: ExportPhase` 直値に揃える)。mermaid `export_cancelling → export_idle: ffmpeg 停止` / `export_cancelling → export_completed: PROGRESS_COMPLETE` ([#837](https://github.com/Idios/kobutachan-allaganeye/issues/837)) と内部 reducer `cancelling → idle (CANCEL_CONFIRMED)` / `cancelling → completed (PROGRESS_COMPLETE)` は同形状 |

### 3.3 「entry-time 特殊状態」「sub-component エラー」の扱い

complete / preview の 2 画面で本 doc は 2 種の状態を **mermaid と非対称** に扱う:

1. **`*_empty` (entry-time 特殊状態)**: `metadata === null` (complete §2.3.11) や `match` 解決失敗 (preview §2.4.15) を「画面 entry 時に発生しうる特殊 idle」として独立状態化。mermaid では entry エッジを暗黙化 (drop → detecting → complete の通常フローで到達しないため)。本 doc は §2.x.N emptyNote と対応付けて明示する
2. **`*_restoreError` (sub-component エラー)**: RestoreButton ([components/RestoreButton.tsx](../gui/src/components/RestoreButton.tsx)) は `restoreError` を inline `role="alert"` で表示する共通 component。mermaid は画面レベル状態として記述するが、本 doc は §2.3.4 / §2.4.13 で RestoreButton 自身の状態 (`idle` / `busy` / `disabled`) として扱い、画面ヘッダの便宜状態列挙からは除外する

両方とも意図的な分担で、**画面間遷移の正準は引き続き ui-architecture.md mermaid**。本 doc の §2.x ヘッダは「画面実装が明示的に持つ状態 + 表示が条件分岐する状態」を列挙する設計で揃えている。

### 3.4 §1 共通原則の例外規定

§2 画面別の記述から派生し、§1 共通原則の例外として明文化したもの:

- **§1.1 例外 (export 画面の session-local config)**: `outDir` / `namePattern` / `codec` / `excludedIndexes` は match 編集ではない一時的な書き出し設定であり `metadataStore` に commit しない (§2.5 ヘッダで宣言)。同様の「画面マウント中のみ有効な session-local config」は今後追加する場合も local state で保持する。`updateMatch` 経由の §1.1 規律は **match 編集 (start/end/name/type) 限定** と読む

## 関連

- 起票元: [#590](https://github.com/Idios/kobutachan-allaganeye/issues/590)
- 直接の根因: [#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) (PreviewScreen 適用ボタンバグ + state mutation 欠落 + silent loss)
- §2 完成後の sync 対象: [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) (Phase 2.5 detecting/complete) / [#466](https://github.com/Idios/kobutachan-allaganeye/issues/466) (Phase 4 export) / [#586](https://github.com/Idios/kobutachan-allaganeye/issues/586) (CompleteScreen 所要列) / [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) (a11y/polish) / [#588](https://github.com/Idios/kobutachan-allaganeye/issues/588) (BrightnessTimeline threshold 連動)
