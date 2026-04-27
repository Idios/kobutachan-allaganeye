# Allagan Eye GUI — UI Interaction Spec

> **スコープ**: 5 画面 (drop / detecting / complete / preview / export) の **UI 部品ごとの操作 → 状態遷移 / store mutation / 例外処理**を明文化する source of truth。画面間遷移は [ui-architecture.md](ui-architecture.md)、画面レイアウトとデザインシステムは [design/README.md](design/README.md)、metadata.json データ契約は [metadata-spec.md](metadata-spec.md) を参照。

本 doc は [#590](https://github.com/Idios/kobutachan-allaganeye/issues/590) で起票し、[#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) (PreviewScreen の state mutation flow / disabled 理由表示 / silent edit loss) の root cause を構造的に再発防止することが第一目的。

## 1. 共通原則

5 画面すべての UI 部品は本節の原則に準拠する。違反は #589 系統のバグとして扱い、レビュー時は本節を逐条照合する。

### 1.1 state mutation flow: input → store → dirty 即時反映

**原則**: フォーム input (text / number / select / textarea / radio / checkbox) は onChange で `metadataStore` の `updateMatch` (もしくは同等 mutation) を **debounce 200ms 経由**で呼び、store の `dirty` フラグを即時に立てる。

| 観点 | 規定 |
|---|---|
| debounce 値 | 200ms (連続入力中の中間値で reducer / re-render が発火しすぎない最小値) |
| auto-save (#517) との関係 | 独立。auto-save 側は別 debounce 500ms で `metadata.draft.json` に書く。UI dirty 反映 (200ms) と disk persist (500ms) を分離 |
| 即時 commit が必要な操作 | toggle (skip / type 切替) / 数値 stepper クリック / プルダウン選択 — debounce せず onChange で同期 commit |
| 例外 (commit しない) | UI 一時表示専用 (フィルタ・検索・ソート選択等)。store に commit しない明示が必要な場合のみ local state でよい |

**アンチパターン**: local state (`useState`) のみで保持し apply ボタン押下時に `updateMatch` を一括コールする設計。dirty バッジ・auto-save・confirm がすべて不発になる。`PreviewScreen` の #589 修正前 ([PreviewScreen.tsx:88-102](../gui/src/screens/PreviewScreen.tsx#L88), [PreviewScreen.tsx:334-343](../gui/src/screens/PreviewScreen.tsx#L334)) がこのパターンに該当した。

**Tip**: フォーカス維持や IME 確定途中に store re-render で input が破壊されるのを避けるため、display 用 controlled value は local state で持ち、onChange で local state を更新しつつ debounce で store に commit する 2 レイヤ実装でよい (local state を捨てるのではなく、commit 経路に乗せる)。

### 1.2 disabled 条件は理由表示必須 (tooltip + inline)

**原則**: ボタン・input の `disabled=true` は必ず理由を表示する。表示は **(a) 当該要素の tooltip (`title` 属性 + `aria-describedby`)** と **(b) 近傍の inline hint (small text)** の両方を提供する。

| 表示形式 | 用途 | 必須範囲 |
|---|---|---|
| tooltip 単独 | 副次ボタン (FrameStrip 内 stepper、行内アイコンボタン等) | 副次 UI |
| inline hint 単独 | 主要 CTA 周辺で常時可視化したい理由 | 主要 CTA は inline 必須 |
| tooltip + inline 併用 | 主要 CTA (適用 / 元に戻す / 書き出し開始 等) | **主要 CTA は両方必須** |

- a11y 上は `aria-describedby` で理由要素の id を参照させる。screen reader が disabled の理由を読み上げる
- inline hint は赤字エラーではなく `var(--ae-text-dim)` 系の補助色。情報レベル
- 理由文は **行動指針を含む形** (例:「サンプル動画では保存できません。実際の動画を選択してください。」)。否定形だけで終わらせない

**アンチパターン**: 理由表示なしの disabled。ユーザーは原因不明で「壊れた」と認識する ([PreviewScreen.tsx:514-518](../gui/src/screens/PreviewScreen.tsx#L514), `applying || !filePath` の sample mode 永続 disabled が #589 該当ケース)。

### 1.3 silent loss 防止: dirty consume 側で confirm

**原則**: `metadataStore.dirty === true` の状態で、編集破棄を伴う操作 (画面遷移・別 match 選択・元に戻す・アプリ終了) が発火する場合、必ず confirm ダイアログを挟む。confirm は標準 `window.confirm()` で十分 (Tauri のネイティブ dialog plugin でも可、ただし全画面で統一)。

| consume 経路 | confirm メッセージ (canonical) | 出現画面 |
|---|---|---|
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

**アンチパターン**: dirty=true なのに confirm せず遷移する設計 ([PreviewScreen.tsx:345-363](../gui/src/screens/PreviewScreen.tsx#L345) の handleBack / handleExport が #589 該当)。

### 1.4 sample mode (filePath==null) の read-only 明示

**原則**: `metadataStore.loadSample()` で読み込まれた sample metadata (`metadataStore.filePath === null`) は **編集不可 (read-only)** として扱い、編集系 UI 部品はすべて grayed out + 上部に常時 hint を表示する。

| 部品種別 | sample mode の扱い |
|---|---|
| 編集 input (start/end TC、name、type/type_override、skip toggle 等) | **disabled** (tooltip 理由表示) |
| 主要 CTA (適用、元に戻す) | **disabled** + inline hint「サンプル動画では保存できません」 |
| 編集を伴わないナビゲーション (画面遷移、行選択、stepper の表示更新等) | **操作可** (学習目的を阻害しない) |
| 開発者向け StateSwitcher (右上 float) | sample mode と独立に常時操作可 |
| 上部 inline banner | 常時表示「サンプル動画です。実際の動画を選択すると保存できます。」 |

検出条件は **`metadataStore.filePath === null`** に集約。`metadata !== null && filePath === null` を「sample である」の唯一の判定として使い、コンポーネント個別に `loadSample` 経由かを推定する分岐を作らない。

### 1.5 エラー表示の一貫性 (inline + toast)

**原則**: 失敗系の表示は **(a) 失敗を引き起こした操作元の inline error** と **(b) 画面右上の global toast** の併用を基本とする。

| 表示チャネル | 用途 | auto-dismiss |
|---|---|---|
| inline error (操作要素直下に赤地 small text) | 直前操作の失敗理由を文脈付きで提示。フォーカスを保持しやすい | しない (操作再試行 / 別操作で消える) |
| global toast (画面右上、`<Toast>` placeholder) | 操作元から離れた箇所で発生したエラー、または短時間で消えてよい要約通知 | 5 秒 (操作要操の通知は permanent 寄り、bg 失敗は短く) |
| inline + toast 併用 | apply / restore / export 等の主要操作の失敗。inline で原因明示 + toast で「保存に失敗しました」要約 | toast のみ 5s、inline は明示 dismiss まで残す |

**文言指針**:

- 技術詳細ではなく行動指針を含める (例: 「Disk full のため保存できませんでした。空き容量を確保してから [再試行] してください」)
- 二段構造: 1 行目で何が起きたか / 2 行目で次の行動 (inline で 2 行、toast は 1 行に圧縮)
- i18n キー素のまま (例: `error.apply.failed`) は禁止

**アンチパターン**: `console.error` のみで UI に出さない / `alert()` で flow を強制停止する / エラー内容を握りつぶして success 扱いにする。

## 2. 画面別 UI 部品状態機械

§2 は 5 画面それぞれを **1 画面 = 1 PR** で順次追加する (#590 着手フローに従う)。

| 節 | 画面 | 主要 UI 部品 | 進捗 |
|---|---|---|---|
| §2.1 | drop | D&D zone / [参照…] / 直近録画リスト / SelectedCard / probeError card | #598 で追加 |
| §2.2 | detecting | AllaganSigil 回転 / Header / progressBadge / PhaseRow ×2 / live log / [中断] | #600 で追加 |
| §2.3 | complete | statusDot / sourceBox / stats / [元に戻す] / [境界を調整] / [全試合書き出し] / [× 閉じる] / BrightnessTimeline / listItem / previewPane / emptyNote | #603 で追加 |
| §2.4 | preview | [◀ 一覧へ] / match name input / type select / Pane (×2 IN/OUT) / Pane.video / Pane.tcInput / stepRow ×6 / keyHint / FrameStrip / [適用] / dirty indicator / applyError / [元に戻す] / [書き出し] / emptyNote | 本 PR で追加 |
| §2.5 | export | 出力先選択 / 命名規則 / コーデック選択 / [書き出し開始] / [中断] / 試合別 progress / [✓ フォルダを開く] / [もう一度書き出す] | TBD |

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
|---|---|
| 種類 | drop zone (div、Phase 3 で `onDrop` ハンドラを実装、現状は visual のみ) |
| 状態 | `idle` (待受) / `dragOver` (Phase 3、ハイライト) / `disabled` (phase=`selecting/probing/selected/probeError` 時は受け付けない) |
| 遷移トリガー | Phase 3: native HTML `drop` event → reducer `DND_DROPPED` → phase `idle → probing` ([#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) でハンドラ実装) |
| store mutation | Phase 3: `setSelectedVideoPath(path)` (ハンドラ内、probe 成功後に発火) |
| 例外 / edge case | 拡張子バリデーション (`.mp4 / .mkv / .avi / .mov`)、複数ファイルドロップ時は最初の 1 件のみ採用、フォルダドロップは reject。**Phase 3 (#465) で実装**: 現状は `RECENT_DUMMY` 表示のみで `onDrop` 未配線 |

#### §2.1.2 [参照…] button

| 項目 | 内容 |
|---|---|
| 種類 | button ([DropScreen.tsx:147-154](../gui/src/screens/DropScreen.tsx#L147)) |
| 状態 | `idle` (phase=`idle/probeError`) / `disabled` (phase=`selecting/probing/selected`) |
| 遷移トリガー | `onClick` → `pickAndProbe()` → reducer `BROWSE_CLICKED` (phase=`idle → selecting`) または `BROWSE_CLICKED` (phase=`probeError → selecting`) |
| store mutation | probe 成功時のみ `appStateStore.setSelectedVideoPath(path)` (この時点ではまだ呼ばれない、§2.1.6 [OK] で発火) |
| 例外 / edge case | 1.2 disabled 理由: selecting 中は `(選択中)` inline テキスト ([:155](../gui/src/screens/DropScreen.tsx#L155))、probing 中は `(解析中)` ([:156](../gui/src/screens/DropScreen.tsx#L156)) を併記。**現状 tooltip は未実装** — §1.2 準拠として `aria-describedby` + `title` を後続 PR で追加 (本 doc が source of truth) |

#### §2.1.3 直近の録画 list

| 項目 | 内容 |
|---|---|
| 種類 | list (各 item は読み取り専用 row、Phase 3 で click ハンドラ追加予定) |
| 状態 | `idle` / `hover` (Phase 3、装飾のみ) / `disabled` (phase=`selecting/probing/selected/probeError` 時は item click を無効化) |
| 遷移トリガー | Phase 3: row `onClick` → 既存 metadata.json 検索 → `setSelectedVideoPath(item.path)` + `navigate('detecting')` (※ probe スキップ — 直近の録画は metadata 既存前提) |
| store mutation | Phase 3: `appStateStore.setSelectedVideoPath` + `navigate('detecting')` |
| 例外 / edge case | item の物理ファイルが移動・削除されている場合は item に「ファイルが見つかりません」inline error + 削除リンク表示。**Phase 3 (TBD)**: 現状は `RECENT_DUMMY` 定数 ([:12-16](../gui/src/screens/DropScreen.tsx#L12)) の 3 行 dummy 表示のみで click 未配線 |

#### §2.1.4 SelectedCard (probe 結果カード)

| 項目 | 内容 |
|---|---|
| 種類 | card (display container、phase=`selected` のときのみ render、[DropScreen.tsx:198-232](../gui/src/screens/DropScreen.tsx#L198)) |
| 状態 | `selected` (probe 結果 + 確認ボタン表示) |
| 遷移トリガー | reducer `PROBE_OK` で phase=`probing → selected` 後に出現 |
| store mutation | カード自体は表示のみ、mutation なし (ボタンは §2.1.5 / §2.1.6) |
| 例外 / edge case | `probeInfo` が null になり得るが、phase=`selected` 時は guard ([:115-116](../gui/src/screens/DropScreen.tsx#L115)) で render しないため不整合は発生しない |

#### §2.1.5 [キャンセル] button (SelectedCard 内)

| 項目 | 内容 |
|---|---|
| 種類 | button ([DropScreen.tsx:223-225](../gui/src/screens/DropScreen.tsx#L223)) |
| 状態 | `idle` (phase=`selected` のみ表示) |
| 遷移トリガー | `onClick` → `cancelSelection()` → reducer `CANCEL_SELECTION` (phase=`selected → idle`) + `setProbeInfo(null)` |
| store mutation | なし (`appStateStore.setSelectedVideoPath` は §2.1.6 でしか呼ばれていないので、リセットも不要) |
| 例外 / edge case | confirm ダイアログなし (まだ §1.3 dirty 編集なし)。Phase 3 で D&D 経由 selection も同 phase に集約されるため挙動を共通化する |

#### §2.1.6 [OK — 検知開始] button (SelectedCard 内)

| 項目 | 内容 |
|---|---|
| 種類 | button ([DropScreen.tsx:226-228](../gui/src/screens/DropScreen.tsx#L226)) |
| 状態 | `idle` (phase=`selected` のみ表示。`probeInfo` が null の場合は `confirm()` 内で early return しているが、本ボタン自体は disabled にしていない — 不整合シナリオを防ぐ最終 guard として機能) |
| 遷移トリガー | `onClick` → `confirm()` → `appStateStore.setSelectedVideoPath(probeInfo.path)` + `navigate('detecting')` |
| store mutation | `appStateStore.setSelectedVideoPath(path)` ([DropScreen.tsx:73](../gui/src/screens/DropScreen.tsx#L73)) + `appStateStore.navigate('detecting')` ([:74](../gui/src/screens/DropScreen.tsx#L74)) |
| 例外 / edge case | navigate 後の detecting 画面で metadata.json load を行うため、本ボタン押下時点ではまだ `metadataStore` は触られていない。`probeInfo` 不整合時は `confirm()` 内で no-op |

#### §2.1.7 probeError card

| 項目 | 内容 |
|---|---|
| 種類 | card (display container、phase=`probeError` のときのみ render、[DropScreen.tsx:117-137](../gui/src/screens/DropScreen.tsx#L117))。`role="alert"` で a11y 通知 |
| 状態 | `probeError` (error 表示 + dismiss / retry ボタン) |
| 遷移トリガー | reducer `PROBE_FAIL` で phase=`probing → probeError` 後に出現 ([DropScreen.tsx:53,67](../gui/src/screens/DropScreen.tsx#L53)) |
| store mutation | カード自体は表示のみ |
| 例外 / edge case | error メッセージは `setError(e.message)` ([:52,66](../gui/src/screens/DropScreen.tsx#L52)) で local state に保存。dialog open 失敗 (file picker plugin のエラー) と probe 失敗 (ffprobe エラー) のいずれもこの card に集約。§1.5 文言指針に従い、ffprobe からの raw stderr ではなく行動指針付きで wrap することが望ましい (現状 raw メッセージ — 後続改善で wrap、本 doc が source of truth) |

#### §2.1.8 [閉じる] button (probeError card 内)

| 項目 | 内容 |
|---|---|
| 種類 | button ([DropScreen.tsx:122-128](../gui/src/screens/DropScreen.tsx#L122)) |
| 状態 | `idle` (phase=`probeError` のみ表示) |
| 遷移トリガー | `onClick` → `dismissError()` → reducer `DISMISS_ERROR` (phase=`probeError → idle`) + `setError(null)` |
| store mutation | なし |
| 例外 / edge case | confirm ダイアログなし (編集なし)。idle に戻ると D&D zone と [参照…] が再度有効化される |

#### §2.1.9 [再試行] button (probeError card 内)

| 項目 | 内容 |
|---|---|
| 種類 | button ([DropScreen.tsx:129-135](../gui/src/screens/DropScreen.tsx#L129)) |
| 状態 | `idle` (phase=`probeError` のみ表示) |
| 遷移トリガー | `onClick` → `pickAndProbe()` → reducer `BROWSE_CLICKED` (phase=`probeError → selecting`) |
| store mutation | なし (probe 成功時の流れは §2.1.2 と同じ) |
| 例外 / edge case | 連続失敗時も常に [閉じる] で `idle` に戻れる。`pickAndProbe()` 内で `setError(null)` するので前回 error は消える |

### §2.2 detecting

**phase**: `running | cancelling | cancelled | completed | error` ([reducers/detecting.ts:16-40](../gui/src/screens/reducers/detecting.ts#L16))

**store**: detecting screen は **`metadataStore.loadSample()` を `phase=completed` で 1 回だけ呼ぶ** ([DetectingScreen.tsx:50-55](../gui/src/screens/DetectingScreen.tsx#L50))。`appStateStore.navigate('drop' | 'complete')` で遷移し、`selectedVideoPath` は読むのみで mutation しない (drop で確定した path を後段が継承する設計、#465 review C)。

**dirty / silent loss**: 編集対象 metadata が無いため §1.3 silent loss confirm の対象外。ただし [中断] → drop 遷移は確定済み video path を捨てる動線なので、Phase 2.5 (#569) で確認 dialog を入れるかは検討事項として残す ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) で議論)。

**sample mode**: `loadSample()` を呼ぶのは detecting だが、これは sample 検出を「実 CLI が走った結果」として代替する Phase 2 の暫定動作。Phase 2.5 (#569) で実 CLI 結果に置き換えれば本画面で sample mode 起動経路は廃止される。

**エラー表示**: §1.5 のうち本画面では現状 **toast を使わず drop へ navigate する Phase 2 暫定挙動** ([DetectingScreen.tsx:65-69](../gui/src/screens/DetectingScreen.tsx#L65))。Phase 2.5 (#569) で `error` phase 時に **toast 通知 + drop 遷移** に置換する。inline は本画面では採用しない (画面が観測フローに専念する設計のため)。

**実装段階**:

- 現状 (Phase 2): 80ms × 100 tick = 8s の dummy progress、log は progress 連動の hardcoded 3 行 ([DetectingScreen.tsx:11-12,118-133](../gui/src/screens/DetectingScreen.tsx#L11))
- Phase 2.5 (#569): 実 CLI stdout streaming に差し替え、log は CLI からの行を逐次 append、`error` toast、`cancelling → cancelled` は実 ffmpeg `kill()` 完了で confirm
- 関連: [#523](https://github.com/Idios/kobutachan-allaganeye/issues/523) (running 中の `× 閉じる` 確保) は本画面の cancel と同じ kill 経路を共有予定

#### §2.2.1 AllaganSigil (回転アニメーション)

| 項目 | 内容 |
|---|---|
| 種類 | 装飾 SVG ([DetectingScreen.tsx:85](../gui/src/screens/DetectingScreen.tsx#L85)、`<AllaganSigil size={84} rotating={phase === 'running'} />`) |
| 状態 | `displayOnly`。phase=`running` のみ回転、それ以外は静止 |
| 遷移トリガー | phase 変化に追従 (props `rotating` の derived value) |
| store mutation | なし |
| 例外 / edge case | アニメーション停止は phase 終端 (cancelled / completed / error) への到達を視覚的に通知する役割。a11y は `role` 未指定 (装飾扱い) |

#### §2.2.2 Header (caption / fileName / meta)

| 項目 | 内容 |
|---|---|
| 種類 | display block ([DetectingScreen.tsx:84-97](../gui/src/screens/DetectingScreen.tsx#L84)) |
| 状態 | `displayOnly` |
| 遷移トリガー | なし。`selectedVideoPath` 変化時に再 render (basename を抜き出して表示) |
| store mutation | なし |
| 例外 / edge case | `selectedVideoPath` が null の場合は `'(video)'` フォールバック ([:80](../gui/src/screens/DetectingScreen.tsx#L80))。Phase 2.5 (#569) で `meta` 行を「dummy probe · Phase 2 skeleton」から実 ffprobe 結果 (解像度 / fps / 長さ等) に差し替える |

#### §2.2.3 progressBadge

| 項目 | 内容 |
|---|---|
| 種類 | display block ([DetectingScreen.tsx:91-96](../gui/src/screens/DetectingScreen.tsx#L91)) |
| 状態 | `displayOnly`。`progress` (0-100) を四捨五入で表示 |
| 遷移トリガー | local state `progress` 変化 (Phase 2 dummy interval、Phase 2.5 で CLI 進捗イベント) |
| store mutation | なし |
| 例外 / edge case | Phase 2 では `progressTiming` 行が `'Phase 2 dummy'` の固定文字列。Phase 2.5 で経過時間 / ETA に差し替え (#569 議論対象) |

#### §2.2.4 PhaseRow.Detecting (粗スキャン)

| 項目 | 内容 |
|---|---|
| 種類 | progress bar ([DetectingScreen.tsx:102-107](../gui/src/screens/DetectingScreen.tsx#L102)、`PhaseRow` コンポーネント) |
| 状態 | bar fill: `pending` (pct=0) / `running` (0<pct<100) / `done` (pct≥100) ([DetectingScreen.tsx:156-178](../gui/src/screens/DetectingScreen.tsx#L156))。phase との対応は無く `pct1` (progress × 1.25) のみで決まる |
| 遷移トリガー | `progress` 変化 (Phase 2 dummy、Phase 2.5 で CLI のフェーズ進捗) |
| store mutation | なし |
| 例外 / edge case | Phase 2 では `pct1` が 80% 時点で 100% 完了する見せ方 (粗スキャンは早く終わる演出)。Phase 2.5 で実フェーズに対応する pct 計算に差し替え |

#### §2.2.5 PhaseRow.Refining (精密計測)

| 項目 | 内容 |
|---|---|
| 種類 | progress bar ([DetectingScreen.tsx:108-113](../gui/src/screens/DetectingScreen.tsx#L108)、`PhaseRow` の 2 個目) |
| 状態 | `pending` / `running` / `done` (§2.2.4 と同じ semantics) |
| 遷移トリガー | `progress` 変化 (Phase 2 dummy では `pct2 = (progress - 40) × 1.67`、progress=40 から開始) |
| store mutation | なし |
| 例外 / edge case | Phase 2 では Detecting 完了相当のタイミング (progress=40) から start。Phase 2.5 で実フェーズ境界に置換 |

#### §2.2.6 live log

| 項目 | 内容 |
|---|---|
| 種類 | append-only display list ([DetectingScreen.tsx:118-133](../gui/src/screens/DetectingScreen.tsx#L118))。`role="log"` + `aria-label="detect log"` で a11y 対応 |
| 状態 | `displayOnly`。Phase 2 は progress 閾値 (0% / 30% / 60%) で 3 行を順次表示する hardcoded 動作 |
| 遷移トリガー | progress 連動 (Phase 2 dummy)。Phase 2.5 で CLI stdout 行を逐次 append |
| store mutation | なし |
| 例外 / edge case | Phase 2.5 で実 CLI stdout に切替時、行数が長期間で増え続けるため scroll 制御 (auto-scroll、最大行数制限) を要設計。retention は描画にのみ影響し store には永続化しない (#569 議論対象) |

#### §2.2.7 [中断] button

| 項目 | 内容 |
|---|---|
| 種類 | button ([DetectingScreen.tsx:136-143](../gui/src/screens/DetectingScreen.tsx#L136)) |
| 状態 | `idle` (phase=`running`) / `disabled` (phase=`cancelling/cancelled/completed/error`) |
| 遷移トリガー | `onClick` → reducer `CANCEL_CLICKED` (phase=`running → cancelling`)。Phase 2 は副作用 effect で即座に `CANCEL_CONFIRMED` を発火し `cancelling → cancelled` 遷移 ([DetectingScreen.tsx:72-76](../gui/src/screens/DetectingScreen.tsx#L72))。Phase 2.5 で実 ffmpeg `kill()` 完了を待ってから `CANCEL_CONFIRMED` |
| store mutation | なし (cancelled 検出後の effect で `appStateStore.navigate('drop')` のみ、[DetectingScreen.tsx:58-62](../gui/src/screens/DetectingScreen.tsx#L58)) |
| 例外 / edge case | §1.2 disabled 理由表示について、現状 `disabled={phase !== 'running'}` のみで tooltip / inline hint 未実装 → 後続 PR で `title="検知実行中のみ中断できます"` 等を追加 (本 doc が source of truth)。`cancelling` 中の連打は disabled で物理的に防止 |

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

**sample mode**: `metadataStore.filePath === null` の sample mode では `[元に戻す]` は `hasBackup=false` で disabled、編集系のない complete 画面では §1.4 の sample banner を上部 `topBar` 直下に表示する (本 doc が source of truth、現状未実装)。

**エラー表示**: §1.5 inline + toast 併用。complete 画面の主要エラー源は `restoreError` ([RestoreButton.tsx:63-67](../gui/src/components/RestoreButton.tsx#L63), inline `role="alert"`)。Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) で global toast 表示先を兼任する設計に揃える。

**実装段階**:

- 現状 (Phase 2): 試合一覧 / BrightnessTimeline / プレビューサムネイル ([#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) で実 path に切替済) が動作。`brightness` は `sampleBrightness()` の固定波形 ([CompleteScreen.tsx:42](../gui/src/screens/CompleteScreen.tsx#L42))
- Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)): 実 video からの brightness 抽出に置換、所要列 ([#586](https://github.com/Idios/kobutachan-allaganeye/issues/586))、a11y / polish ([#587](https://github.com/Idios/kobutachan-allaganeye/issues/587))、threshold 連動 ([#588](https://github.com/Idios/kobutachan-allaganeye/issues/588))、§1.3 dirty consume confirm 全経路を実装

#### §2.3.1 statusDot

| 項目 | 内容 |
|---|---|
| 種類 | 装飾 (`<div aria-hidden="true">`、[CompleteScreen.tsx:65](../gui/src/screens/CompleteScreen.tsx#L65)) |
| 状態 | `displayOnly` |
| 遷移トリガー | なし (常時可視) |
| store mutation | なし |
| 例外 / edge case | 常時 gold 点。Phase 2.5 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569)) で「sample mode は別色」「dirty 時は瞬き」等の議論余地あり (本 doc 範囲外、議論時は §1.4 / §1.3 と整合させる) |

#### §2.3.2 sourceBox (caption + filename)

| 項目 | 内容 |
|---|---|
| 種類 | display block ([CompleteScreen.tsx:66-69](../gui/src/screens/CompleteScreen.tsx#L66)) |
| 状態 | `displayOnly`。`metadata.source` を full path で表示 |
| 遷移トリガー | `metadata` 変化に追従 |
| store mutation | なし |
| 例外 / edge case | full path が長すぎる場合の overflow / ellipsis は CSS 任せ。a11y は plain text、screen reader はそのまま読み上げる。Phase 2.5 で basename + tooltip full path に変更する選択肢あり ([#587](https://github.com/Idios/kobutachan-allaganeye/issues/587)) |

#### §2.3.3 stats (試合数 / 総尺)

| 項目 | 内容 |
|---|---|
| 種類 | display group ([CompleteScreen.tsx:70-81](../gui/src/screens/CompleteScreen.tsx#L70)) |
| 状態 | `displayOnly`。`metadata.matches.length` と `metadata.source_duration_display` を表示 |
| 遷移トリガー | `metadata` 変化に追従 |
| store mutation | なし |
| 例外 / edge case | `matches.length === 0` の場合 `0` 表示 (後段の listItem は空、previewPane は非表示 = §2.3.10)。Phase 2.5 で「合計試合長」「FL 比率」等の追加列が議論対象 ([#586](https://github.com/Idios/kobutachan-allaganeye/issues/586)) |

#### §2.3.4 [元に戻す] button (RestoreButton)

| 項目 | 内容 |
|---|---|
| 種類 | button + inline error ([RestoreButton.tsx:53-69](../gui/src/components/RestoreButton.tsx#L53)) |
| 状態 | `idle` (`hasBackup=true` && `restoring=false`) / `busy` (`restoring=true`、ラベル `…`) / `disabled` (`hasBackup=false` または `restoring=true`) |
| 遷移トリガー | `onClick` → `confirmFn(confirmMessage)` で確認 → OK なら `metadataStore.restore()` (atomic copy `metadata.original.json` → `metadata.json`) → 成功なら `onRestored?` callback |
| store mutation | `metadataStore.restoring`, `metadataStore.metadata` (再 load), `metadataStore.dirty=false` (apply の rollback として), `metadataStore.hasBackup` (`refreshBackupStatus`) |
| 例外 / edge case | confirm キャンセル → 何もしない。restore 失敗 → `restoreError` を inline `role="alert"` で表示。complete 画面では `onRestored` 未指定 (preview 画面は navigate('complete') を渡す)。§1.2 通り disabled 理由 tooltip ("バックアップが存在しません" / "復元中") は現状未実装、後続で追加 |

#### §2.3.5 [境界を調整] button

| 項目 | 内容 |
|---|---|
| 種類 | button ([CompleteScreen.tsx:84-94](../gui/src/screens/CompleteScreen.tsx#L84)) |
| 状態 | `idle` (selectedMatch あり) / `disabled` (`!selectedMatch`、つまり `matches=[]`) |
| 遷移トリガー | `onClick` → `appStateStore.openPreviewFor(selectedMatch.index)` (内部で `selectMatch` + `navigate('preview')`) |
| store mutation | `appStateStore.selectedMatchIndex`, `appStateStore.screen='preview'` |
| 例外 / edge case | §1.3 dirty=true 時の confirm が現状未実装 (canonical: 「未保存の変更があります。破棄して別の試合を開きますか？」)。後続で `if (dirty) confirm(...)` を入れる必要あり。§1.2 disabled 理由 tooltip ("試合が選択されていません") は現状未実装 |

#### §2.3.6 [全試合書き出し] button

| 項目 | 内容 |
|---|---|
| 種類 | button ([CompleteScreen.tsx:95-101](../gui/src/screens/CompleteScreen.tsx#L95)) |
| 状態 | `idle` (現状無条件で活性) |
| 遷移トリガー | `onClick` → `navigate('export')` |
| store mutation | `appStateStore.screen='export'` |
| 例外 / edge case | `matches.length === 0` でも活性 (export 画面で空状態を扱う想定)、Phase 2.5 で「試合 0 件のときは disabled + 理由表示」とするかは [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) で議論。§1.3 dirty=true confirm が未実装、後続で実装 (canonical: 「未保存の変更があります。破棄して書き出しへ進みますか？」) |

#### §2.3.7 [× 閉じる] button

| 項目 | 内容 |
|---|---|
| 種類 | button ([CompleteScreen.tsx:102-109](../gui/src/screens/CompleteScreen.tsx#L102)) |
| 状態 | `idle` (現状無条件で活性) |
| 遷移トリガー | `onClick` → `handleClose()` ([CompleteScreen.tsx:56-60](../gui/src/screens/CompleteScreen.tsx#L56)) → `clear()` + `appReset()` + `navigate('drop')` |
| store mutation | `metadataStore` 全 reset、`appStateStore` 全 reset、`appStateStore.screen='drop'` |
| 例外 / edge case | §1.3 dirty=true 時の confirm が未実装。**現状 silent loss する** ([#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) 系の root cause)。canonical: 「未保存の変更があります。破棄してファイル選択へ戻りますか？」を後続で必須実装 |

#### §2.3.8 BrightnessTimeline (match block click)

| 項目 | 内容 |
|---|---|
| 種類 | SVG component ([BrightnessTimeline.tsx](../gui/src/components/BrightnessTimeline.tsx))。grid / threshold line / blackout bands / brightness line+fill / match blocks / time axis の合成 |
| 状態 | `displayOnly` (子要素 grid / threshold / blackouts / line / axis) + interactive (match blocks)。match block の visual: `selectedIndex` 一致で opacity=1 + stroke、それ以外で opacity=0.55 |
| 遷移トリガー | match block (`<g>`) `onClick` → `props.onSelectMatch(index)` → `appStateStore.selectMatch(index)` |
| store mutation | `appStateStore.selectedMatchIndex` |
| 例外 / edge case | `threshold` prop は現状 hardcoded default 15、Phase 2.5 ([#588](https://github.com/Idios/kobutachan-allaganeye/issues/588)) で `metadata.detection_params.blackout_threshold` 連動に置換予定。`samples` は Phase 2 で `sampleBrightness()` 固定、Phase 2.5 で実 video の brightness CSV / array に置換 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569))。selectedIndex の同期は listItem (§2.3.9) と双方向 |

#### §2.3.9 試合一覧 listItem (single + double click)

| 項目 | 内容 |
|---|---|
| 種類 | `<li>` ([CompleteScreen.tsx:128-160](../gui/src/screens/CompleteScreen.tsx#L128))。MatchThumb / 試合名 + 開始→終了 + duration / typeBadge (FL / ?) を内包 |
| 状態 | `idle` / `active` (selectedMatchIndex 一致時 `listItemActive` クラス + `data-selected="true"`) |
| 遷移トリガー | single `onClick` → `selectMatch(index)` (選択のみ) / `onDoubleClick` → `openPreviewFor(index)` (選択 + preview 遷移) |
| store mutation | single click: `appStateStore.selectedMatchIndex` のみ。double click: 加えて `appStateStore.screen='preview'` |
| 例外 / edge case | §1.3 dirty=true 時に別 match を double click すると編集破棄が発生 → confirm 必須 (現状未実装、§2.3.5 [境界を調整] と同等の対応)。listItem 内 typeBadge は表示専用で click 影響なし。`name` は `match.name ?? "MATCH_NNN"` フォールバック ([metadata-spec.md](metadata-spec.md) 編集契約により `name` は GUI 表示専用、metadata.json には書き戻さない) |

#### §2.3.10 previewPane (display)

| 項目 | 内容 |
|---|---|
| 種類 | display block ([CompleteScreen.tsx:165-208](../gui/src/screens/CompleteScreen.tsx#L165))。MatchThumb (large) + previewPlayOverlay + previewMeta (title + 開始 / 終了 / 長さ / 分類) |
| 状態 | `displayOnly` (selectedMatch 存在時のみ render、`!selectedMatch` で section 全体非表示) |
| 遷移トリガー | `selectedMatch` 変化に追従 (selectMatch / openPreviewFor / 1-match auto-select 経由) |
| store mutation | なし |
| 例外 / edge case | previewPlayOverlay は装飾のみで現状クリック無効 (preview 画面遷移は §2.3.5 / §2.3.9 経由)、Phase 2.5 で「サムネクリック → preview」を追加するかは [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) / [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) で議論。pane の右下に存在した `[境界を調整]` ボタンは [#464](https://github.com/Idios/kobutachan-allaganeye/issues/464) review でトップアクションバーに移動済み (短い viewport で fold 下に隠れるため) |

#### §2.3.11 emptyNote

| 項目 | 内容 |
|---|---|
| 種類 | display ([CompleteScreen.tsx:44-50](../gui/src/screens/CompleteScreen.tsx#L44)) |
| 状態 | `complete_empty` のみ表示 (`metadata === null`)。文言: `'No metadata. Run detect first.'` |
| 遷移トリガー | `metadata` が null になった瞬間 (clear / 起動直後 / load 失敗後) |
| store mutation | なし |
| 例外 / edge case | 通常フロー (drop → detecting → complete) では到達しない (detecting 完了で `loadSample()` が必ず呼ばれる)。dev 用 StateSwitcher で複数 screen を試行する場合や、Phase 2.5 で `clear()` 経由で意図的に表示する経路が増えた場合の文言 / アクションリンク ([参照…] への戻り) は [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) で議論 |

### §2.4 preview

**phase**: 専用 reducer なし。便宜上の状態名 ([ui-architecture.md](ui-architecture.md) §preview の mermaid に対応):

- `preview_empty` — `match` が見つからない (`emptyNote` 表示)
- `preview_idle` — match あり、操作待機
- `preview_applying` — `metadataStore.applying=true` ([適用] in-flight)
- `preview_applyError` — `metadataStore.applyError !== null`
- `preview_restoring` — `metadataStore.restoring=true` (RestoreButton in-flight)

これらは `metadataStore` のフィールド合成で表現され、追加 reducer は持たない。

**editing**: 編集対象パネルを示す local state `editing: 'start' | 'end'` ([PreviewScreen.tsx:88](../gui/src/screens/PreviewScreen.tsx#L88))。`editing` で `currentT` / `setCurrentT` / `activeVideoRef` が分岐し、stepRow / keyboard / FrameStrip の操作対象を決める。`editing` は phase とは独立で、画面マウント中は常に `'start' | 'end'` のいずれか。

**store**: 読み書きは `metadataStore` の `metadata`, `dirty`, `applying`, `applyError`, `filePath`, `updateMatch`, `apply` と `appStateStore` の `selectedMatchIndex`, `navigate`, `selectedVideoPath`。書き込み経路は `updateMatch` ([適用] 押下時のみ、§1.1 違反 → 後述) / `apply` ([適用]) / `RestoreButton.restore` (§2.4.13) / `navigate` (back / export) のみ。

**dirty / silent loss**: §1.3 に従い `handleBack` / `handleExport` が `if (dirty) confirm(...)` を実装済み ([PreviewScreen.tsx:345-363](../gui/src/screens/PreviewScreen.tsx#L345))。**ただし §1.1 違反 (matchName / matchType / startT / endT が local state-only) のため `dirty` が立たず、confirm が `false` 経路に常時 fall-through し silent loss する** ([#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) cascading)。後続の §1.1 修正で confirm が機能し始める設計。

**sample mode**: §1.4 通り `metadataStore.filePath === null` で sample 扱い。現状 [適用] のみ disabled ([PreviewScreen.tsx:518](../gui/src/screens/PreviewScreen.tsx#L518) の `applying || !filePath`) で、(1) 編集 input (matchName / matchType / startT / endT / TC) は disabled になっておらず、(2) 上部 sample banner が未表示、(3) [適用] disabled の理由 tooltip / inline hint が未表示 → §1.2 / §1.4 違反。後続で §1.4 完全準拠に揃える ([#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) で対応)。

**エラー表示**: §1.5 inline + toast 併用。preview 画面の主要エラー源:

- `applyError` → inline `role="alert"` 表示済み ([PreviewScreen.tsx:524-528](../gui/src/screens/PreviewScreen.tsx#L524))
- `restoreError` → RestoreButton 内 inline `role="alert"` 表示済み (§2.3.4 と共通)
- `videoError` (register_video 失敗) → Pane 内 inline `role="alert"` 表示済み ([PreviewScreen.tsx:614-617](../gui/src/screens/PreviewScreen.tsx#L614))

global toast への昇格は Phase 2.5 / [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) で complete 画面と統一する。

**実装段階**:

- 現状 (Phase 3 = [#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) 完了): `<video>` + axum 配信、`requestVideoFrameCallback` ベースのフレームシーク、ffmpeg サムネキャッシュ、キーボードショートカット ←→ 1s / Shift 10s / Alt 1F / Space 再生、TC HH:MM:SS.FF 入力、frame-grid snap、source_fps 連動 (60/120/240) などが完成
- 未対応 (#589 で解消予定): §1.1 state mutation / §1.2 disabled 理由 / §1.4 sample mode read-only — 本 §2.4 が source of truth
- ffmpeg 中断保護 ([#523](https://github.com/Idios/kobutachan-allaganeye/issues/523)): preview では subprocess を持たない (axum 直接配信、サムネは短命) ため、本画面は対象外

#### §2.4.1 [◀ 一覧へ] back button

| 項目 | 内容 |
|---|---|
| 種類 | button ([PreviewScreen.tsx:370-376](../gui/src/screens/PreviewScreen.tsx#L370)) |
| 状態 | `idle` (常時活性) |
| 遷移トリガー | `onClick` → `handleBack()` ([PreviewScreen.tsx:345-353](../gui/src/screens/PreviewScreen.tsx#L345)) → `if (dirty) confirm('未適用の変更があります。破棄して戻りますか？')` → OK で `navigate('complete')` |
| store mutation | `appStateStore.screen='complete'` |
| 例外 / edge case | §1.3 canonical 文言 (「未保存の変更があります。破棄して一覧へ戻りますか？」) と現行文言 (「未適用の変更があります。破棄して戻りますか？」) に差異あり、§1.3 表との表記統一を後続で検討。§1.1 修正前は `dirty=false` 常時で confirm 経路に入らず silent loss |

#### §2.4.2 match name input

| 項目 | 内容 |
|---|---|
| 種類 | text input ([PreviewScreen.tsx:380-386](../gui/src/screens/PreviewScreen.tsx#L380)) |
| 状態 | `idle` (常時活性、sample mode でも disabled になっていない → §1.4 違反) |
| 遷移トリガー | `onChange` → local `setMatchName(value)` のみ。store には commit されない (#589 / §1.1 違反) |
| store mutation | **現状なし** ([適用] 押下時にまとめて `updateMatch({ name })` される) |
| 例外 / edge case | §1.1 canonical: onChange で `updateMatch(match.index, { name: value })` を debounce 200ms 経由で呼ぶ。`name` は metadata.json には書き戻されず GUI 表示専用 ([metadata-spec.md](metadata-spec.md))、placeholder は `match_NNN` フォールバック。空文字許容 (placeholder 表示) |

#### §2.4.3 type select

| 項目 | 内容 |
|---|---|
| 種類 | `<select>` ([PreviewScreen.tsx:393-405](../gui/src/screens/PreviewScreen.tsx#L393))。option: `fl_match` / `unknown` / `skip` |
| 状態 | `idle` (常時活性、sample mode でも disabled になっていない → §1.4 違反) |
| 遷移トリガー | `onChange` → local `setMatchType(value)` のみ。store には commit されない (§1.1 違反) |
| store mutation | **現状なし** ([適用] 押下時にまとめて `updateMatch({ type_override })` される) |
| 例外 / edge case | §1.1 canonical: onChange で `updateMatch(match.index, { type_override: value })` を **即時 commit** (toggle / 単一選択型は §1.1 例外で debounce しない)。`skip` は metadata.json に書き戻されない GUI ローカル情報 ([metadata-spec.md](metadata-spec.md) 編集契約) |

#### §2.4.4 Pane button (activate IN / OUT)

| 項目 | 内容 |
|---|---|
| 種類 | button ([PreviewScreen.tsx:567-572](../gui/src/screens/PreviewScreen.tsx#L567))。IN (start) / OUT (end) の 2 個。`aria-pressed={active}` |
| 状態 | `inactive` / `active` (`editing === 'start'` で IN、`'end'` で OUT) |
| 遷移トリガー | `onClick` → `props.onActivate()` → `setEditing('start' \| 'end')` |
| store mutation | なし (local state) |
| 例外 / edge case | inactive Pane の video / tcInput クリックは `onActivate()` を呼んだ後に play/pause / TC 編集に進む 2 段経路 (§2.4.5 / §2.4.6 で詳述)。`active` 切替で `currentT` / `setCurrentT` / `activeVideoRef` の参照が IN/OUT 間で切り替わる |

#### §2.4.5 Pane.video (`<video>`)

| 項目 | 内容 |
|---|---|
| 種類 | `<video>` ([PreviewScreen.tsx:574-613](../gui/src/screens/PreviewScreen.tsx#L574))。axum 配信 URL を `src` に持つ HTML5 player、`controls={false}` |
| 状態 | `loading` (videoUrl null && videoError null → `loading video…` 表示) / `error` (videoError あり → inline `role="alert"`) / `paused` (default、currentTime ↔ startT/endT 双方向同期) / `playing` (`onTimeUpdate` で startT/endT を currentTime に追従) |
| 遷移トリガー | `onClick` → stopPropagation。inactive なら `onActivate()` のみ、active なら `play()` / `pause()` toggle。`onTimeUpdate` (playing 時のみ) → `onTChange(v.currentTime)` で local state に sync |
| store mutation | なし。local state `setStartT` / `setEndT` を介して TC を更新 |
| 例外 / edge case | paused 中のみ state→video の seek effect ([PreviewScreen.tsx:162-192](../gui/src/screens/PreviewScreen.tsx#L162))。`v.paused` guard なしだと再生中の onTimeUpdate → setStartT → effect → backward seek の loop で再生がガタつく。Space キーでも再生 / 停止可 (global keyboard handler、§2.4.7 注記)。loading / error 時は `<video>` 自体が render されないため click / keyboard はパススルー |

#### §2.4.6 Pane.tcInput (TC manual entry)

| 項目 | 内容 |
|---|---|
| 種類 | text input ([PreviewScreen.tsx:622-631](../gui/src/screens/PreviewScreen.tsx#L622))。`H:MM:SS.FF` 形式 (FF は frame portion、`source_fps` 連動) |
| 状態 | `idle` (常時活性、sample mode でも disabled になっていない → §1.4 違反) |
| 遷移トリガー | `onChange` → `parseTimecode(value, fps)` → 解析成功時 `onTChange(parsed)` (= local `setStartT` / `setEndT`)。`onClick` → stopPropagation で Pane の activate を抑止 |
| store mutation | なし (local state)。§1.1 違反は §2.4.2 / §2.4.3 と同じ性質 |
| 例外 / edge case | `parseTimecode` が null を返す (malformed input) 場合は何もしない (input value は ユーザー編集中の状態を維持)。表示は `fmtPreciseTime(t, fps)` で常に正規化された TC を出すため、playback 中はフレーム単位で値が動く。frame portion は `parseInt(f, 10) / fps` で 60/120/240 fps に対応 |

#### §2.4.7 stepRow buttons (×6)

| 項目 | 内容 |
|---|---|
| 種類 | button × 6 ([PreviewScreen.tsx:433-482](../gui/src/screens/PreviewScreen.tsx#L433))。`-10s / -1s / -1F / +1F / +1s / +10s`。`title="<label> (<key hint>)"` で keyboard 等価操作明示、`aria-label="nudge <label>"` |
| 状態 | `idle` (常時活性) |
| 遷移トリガー | `onClick` → frame ボタンは `nudgeFrame(±1)` (frame-grid snap)、秒 ボタンは `nudge(±1 \| ±10)` (累積) → 内部で `setCurrentT(...)` |
| store mutation | なし (local state) |
| 例外 / edge case | global keyboard ([PreviewScreen.tsx:290-319](../gui/src/screens/PreviewScreen.tsx#L290)) が ←/→/Shift+←→/Alt+←→ に同等の `nudge` / `nudgeFrame` を割り当てる。INPUT/TEXTAREA/SELECT に focus 中はキーボードを `return` で吸わない (TC input への入力を妨げない)。frame-grid snap は IEEE 754 丸め誤差で `t + 1/fps` の frame portion が advance しないケースを回避するため frame 番号ベースで step (例: 2438.75 + 1/120 → frame .90 のままバグ) |

#### §2.4.8 keyHint display

| 項目 | 内容 |
|---|---|
| 種類 | display block ([PreviewScreen.tsx:486-500](../gui/src/screens/PreviewScreen.tsx#L486))。`role="note"` + `aria-label="keyboard shortcuts"`、`<kbd>` で各キー表示 |
| 状態 | `displayOnly` |
| 遷移トリガー | なし (常時可視) |
| store mutation | なし |
| 例外 / edge case | stepRow / global keyboard handler の操作可能性を初学者にも提示する役割。Phase 2.5 で `←/→ ⌥ Shift Space` を OS (mac/win) 別表記に切り替えるかは [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) a11y/polish で議論 |

#### §2.4.9 FrameStrip

| 項目 | 内容 |
|---|---|
| 種類 | sub-component ([PreviewScreen.tsx:502-511](../gui/src/screens/PreviewScreen.tsx#L502))。±3s 範囲、12 frames @ 0.5s 間隔、現境界中心の thumb 列 |
| 状態 | `displayOnly` (frame の sample) + interactive (frame click) |
| 遷移トリガー | thumb `onClick` → `props.onSelectFrame(t)` → `setCurrentT(t)` (= startT / endT 切替に応じて) |
| store mutation | なし (local state) |
| 例外 / edge case | `editing` で `inThumbs` / `outThumbs` を切替表示。thumbs の生成は ffmpeg `generate_match_thumbnails` (Rust 経由) で、boundary が 0.5s 以上動いた時のみ再フェッチ。失敗時は空配列 (UI は空 strip 表示)、エラー文言は出さない (#465 設計判断) |

#### §2.4.10 [適用] primary button

| 項目 | 内容 |
|---|---|
| 種類 | button ([PreviewScreen.tsx:514-522](../gui/src/screens/PreviewScreen.tsx#L514))。`aria-label="apply"` |
| 状態 | `idle` (`!applying && filePath !== null`) / `applying` (label = `'適用中…'`) / `disabled` (`applying \|\| !filePath`) |
| 遷移トリガー | `onClick` → `handleApply()` ([PreviewScreen.tsx:334-343](../gui/src/screens/PreviewScreen.tsx#L334)) → `updateMatch(index, { name, type_override, edited })` で local state を一括 commit → `filePath` がある場合のみ `apply()` を await |
| store mutation | `metadataStore.metadata.matches[i].name / type_override / edited`、`metadataStore.dirty=true` (`updateMatch` 経由)、`metadataStore.applying`、`metadataStore.applyError`、`metadataStore.loadedMtimeMs` (apply 成功時)、`metadataStore.hasBackup` (`refreshBackupStatus`)、`metadataStore.metadata.draft.json` clear ([#517](https://github.com/Idios/kobutachan-allaganeye/issues/517) draft auto-save 連携) |
| 例外 / edge case | sample mode (`filePath === null`) では disabled。**§1.2 違反**: tooltip / inline hint で「サンプル動画では保存できません」を出す canonical を後続で実装。**§1.1 違反**: 本来 onChange ごとに `updateMatch` を debounce 200ms で commit しておき、handleApply は `apply()` だけ呼べばよい。現状の一括 commit は dirty バッジ・auto-save・confirm を全部不発にする設計上の罠 (#589 root cause)。conflict 時は ConflictModal ([metadata-spec.md](metadata-spec.md) §排他管理) が global で表示される (本画面では特段の追加処理なし) |

#### §2.4.11 dirty indicator

| 項目 | 内容 |
|---|---|
| 種類 | display badge ([PreviewScreen.tsx:523](../gui/src/screens/PreviewScreen.tsx#L523))。`● 未保存の変更` 文言 |
| 状態 | `displayOnly`。`dirty=true` のみ render |
| 遷移トリガー | `metadataStore.dirty` 変化に追従 |
| store mutation | なし |
| 例外 / edge case | §1.1 違反のため **現状ほぼ表示されない** (handleApply の updateMatch でいったん true になるが、続く apply() が成功すると即 false)。§1.1 修正後は編集中常時表示される設計 (#589 受け入れ条件 B) |

#### §2.4.12 applyError inline

| 項目 | 内容 |
|---|---|
| 種類 | inline error ([PreviewScreen.tsx:524-528](../gui/src/screens/PreviewScreen.tsx#L524))。`role="alert"` |
| 状態 | `displayOnly`。`applyError !== null` のみ render |
| 遷移トリガー | `metadataStore.applyError` 変化に追従 (apply 失敗で set、次の apply 試行で clear) |
| store mutation | なし |
| 例外 / edge case | dismiss UI 未実装 (再 apply で消える設計)、conflict は別経路 (ConflictModal) のため本 inline には出ない。Phase 2.5 で global toast への昇格 ([#569](https://github.com/Idios/kobutachan-allaganeye/issues/569))、文言の §1.5 行動指針化 (canonical: 「保存に失敗しました。<原因>。<次の行動>」) を実装 |

#### §2.4.13 [元に戻す] (RestoreButton)

| 項目 | 内容 |
|---|---|
| 種類 | RestoreButton 共通 component ([PreviewScreen.tsx:529](../gui/src/screens/PreviewScreen.tsx#L529))。`onRestored={() => navigate('complete')}` で復元成功後に complete へ戻る |
| 状態 | §2.3.4 と共通 (`idle` / `busy` / `disabled`) |
| 遷移トリガー | confirm → `restore()` → 成功で `onRestored` callback → `navigate('complete')` |
| store mutation | §2.3.4 と共通。preview 画面では navigate('complete') が追加発火 |
| 例外 / edge case | restore はディスク上の `metadata.json` を上書きするため、画面遷移を伴わずに preview に留まると編集中の local state (startT / endT 等) が新しい match と矛盾する。これを回避するため preview からは `onRestored` で必ず complete に戻す設計 (§2.3.4 では callback 未指定で同画面に留まる)。§1.2 disabled 理由 tooltip 未実装は §2.3.4 と同じ TODO |

#### §2.4.14 [書き出し] secondary button

| 項目 | 内容 |
|---|---|
| 種類 | button ([PreviewScreen.tsx:530-536](../gui/src/screens/PreviewScreen.tsx#L530)) |
| 状態 | `idle` (常時活性) |
| 遷移トリガー | `onClick` → `handleExport()` ([PreviewScreen.tsx:355-363](../gui/src/screens/PreviewScreen.tsx#L355)) → `if (dirty) confirm('未適用の変更があります。破棄して書き出しに進みますか？')` → OK で `navigate('export')` |
| store mutation | `appStateStore.screen='export'` |
| 例外 / edge case | §2.4.1 と同じく §1.3 canonical 文言と現行文言が異なり、§1.1 修正前は dirty=false 常時で confirm が機能せず silent loss。後続で文言統一 + §1.1 修正 |

#### §2.4.15 emptyNote

| 項目 | 内容 |
|---|---|
| 種類 | display ([PreviewScreen.tsx:326-332](../gui/src/screens/PreviewScreen.tsx#L326))。文言: `'No match selected.'` |
| 状態 | `preview_empty` のみ表示 (`match` が見つからない、つまり `selectedMatchIndex` が `metadata.matches` のどれとも一致しない) |
| 遷移トリガー | `selectedMatchIndex` または `metadata.matches` 変化で `match` が解決できなくなった時 |
| store mutation | なし |
| 例外 / edge case | 通常フロー (complete から double-click / [境界を調整]) では到達しない。dev StateSwitcher で preview に直接遷移したり、apply 後 matches 配列が変動して selectedMatchIndex が消えた場合に表示。文言と「complete へ戻る」リンクは [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) a11y/polish で議論 |

## 3. 既存 doc との分担

| doc | スコープ |
|---|---|
| [ui-architecture.md](ui-architecture.md) | screen / phase 2 層 state machine、screen 間遷移、コンポーネント階層、CSS Modules 慣例、性能目標 |
| [design/README.md](design/README.md) | デザインシステム (色 / タイポ)、画面レイアウト原本 (handoff bundle)、各画面の機能仕様 |
| [metadata-spec.md](metadata-spec.md) | metadata.json スキーマ・読み書き契約 (CLI / GUI 共通)・排他管理 (#514) ・draft auto-save (#517) |
| **本 doc** | **各画面 UI 部品ごとの操作 → store mutation → 例外処理の状態機械 + 共通原則** |

責務の境界:

- **画面間遷移は ui-architecture.md** が source of truth。本 doc は画面間遷移を再記述しない (「→ navigate('complete')」程度の参照のみ)
- **ピクセル / 色 / タイポは design/README.md** が source of truth。本 doc は disabled の見た目等を「`var(--ae-text-dim)` 系」のような token 参照で記述
- **metadata.json の field 仕様は metadata-spec.md** が source of truth。本 doc は store mutation の対象 field を field 名のみで参照

## 関連

- 起票元: [#590](https://github.com/Idios/kobutachan-allaganeye/issues/590)
- 直接の根因: [#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) (PreviewScreen 適用ボタンバグ + state mutation 欠落 + silent loss)
- §2 完成後の sync 対象: [#569](https://github.com/Idios/kobutachan-allaganeye/issues/569) (Phase 2.5 detecting/complete) / [#466](https://github.com/Idios/kobutachan-allaganeye/issues/466) (Phase 4 export) / [#586](https://github.com/Idios/kobutachan-allaganeye/issues/586) (CompleteScreen 所要列) / [#587](https://github.com/Idios/kobutachan-allaganeye/issues/587) (a11y/polish) / [#588](https://github.com/Idios/kobutachan-allaganeye/issues/588) (BrightnessTimeline threshold 連動)
