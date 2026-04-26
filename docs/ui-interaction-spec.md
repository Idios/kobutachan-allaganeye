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

§2 は 5 画面それぞれを **1 画面 = 1 PR** で順次追加する (#590 着手フローに従う)。本 PR では §1 と skeleton のみ。

| 節 | 画面 | 主要 UI 部品 (予定) | 担当 issue ([#590](https://github.com/Idios/kobutachan-allaganeye/issues/590) sub-task) |
|---|---|---|---|
| §2.1 | drop | D&D zone / [参照...] / 直近録画リスト / [OK] / [キャンセル] / [再試行] | TBD |
| §2.2 | detecting | 4 phase progress bar / live log / [中断] / 紋章アニメーション | TBD |
| §2.3 | complete | 輝度タイムライン / 試合一覧行 / [境界を調整] / [全試合書き出し] / [元に戻す] / [× 閉じる] | TBD |
| §2.4 | preview | IN/OUT 2 video / FrameStrip / stepper / TC input / 試合名・type input / [適用] / [元に戻す] / [◀ 一覧へ] / [書き出し] | TBD |
| §2.5 | export | 出力先選択 / 命名規則 / コーデック選択 / [書き出し開始] / [中断] / 試合別 progress / [✓ フォルダを開く] / [もう一度書き出す] | TBD |

各節の記述フォーマット (案):

```text
### §2.X.N <部品名>

| 項目 | 内容 |
|---|---|
| 種類 | button / input / select / list item / drop zone / progress bar / etc |
| 状態 | idle / focus / hover / disabled / loading / error / saving / readonly |
| 遷移トリガー | onChange / onClick / store change / external file event |
| store mutation | どの state を更新するか (ない場合は「なし」) |
| 例外 / edge case | 該当 §1 共通原則の番号付き参照 |
```

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
