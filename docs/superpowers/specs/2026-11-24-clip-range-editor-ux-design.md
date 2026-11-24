# クリップ範囲エディタの UX 再設計 (2026-11-24 / v2)

- **日付**: 2026-11-24（v2: 同日、外部レビュー反映）
- **issue**: [#1156](https://github.com/Idios/kobutachan-allaganeye/issues/1156)
- **目的**: #1139 で導入した「クリップ範囲の調整画面」(`ClipRangeView`) に対する
  Idios の指摘 — **「切り抜き範囲の秒数をどう変えるのか UI が分かりにくい」** — を、
  情報設計のレベルで解く
- **前提（状態の正）**:
  - 画面の実体は [`gui/src/screens/ClipRangeView.tsx`](../../../gui/src/screens/ClipRangeView.tsx)。
    `PreviewScreen` が `clipRange` を積まれて呼ばれたときだけ、試合境界エディタの
    代わりに早期 return で描画する
  - 部品仕様の正は [`docs/ui-interaction-spec.md`](../../ui-interaction-spec.md) §2.4.18。
    本 note の実装完了後に同 § を更新する
  - 範囲の算出規則の正は `allaganeye/export/clips.py`、GUI 側の鏡は
    [`gui/src/utils/clipWindow.ts`](../../../gui/src/utils/clipWindow.ts)
- **レビュー**: Kimi（Claude / Fable 代行）による read-only レビューを 2026-11-24 に実施。
  High 6 / Medium 6 / Low 2 の指摘を本 v2 に反映（§13 に changelog）

## 0. 射程

```text
ClipsScreen ──[この範囲を確認]──┐
IndicatorsScreen ──[行クリック]──┤
                                ▼
              screen='preview' + clipRange
                                │
                                ▼
        PreviewScreen ──(clipMode)──▶ ClipRangeView   ← 本 note の対象
                    └─(通常)──────▶ 試合境界エディタ   ← 対象外
```

試合境界エディタ（`docs/ui-interaction-spec.md` §2.4）は**対象外**。
共通部品 `TimecodePane` を触るのは `onFocus` の追加 1 点だけ（§11 R3）。

**スコープ追加（v2）**: `pre` / `post` / `gap` を `ClipsScreen` の local state から
`appStateStore` の session 設定へ移す（§6 D1）。理由は、この 3 値が baseline の
定義に直接入るため、画面遷移で失われると「表示した自動範囲」と「実際に切り抜く
範囲」が食い違うからである（レビュー指摘 1）。

## 1. 現状の認知負荷と齟齬（コードで確認した順）

| # | 症状 | 根拠 |
| --- | --- | --- |
| A | 秒数を変える入口が 3 系統あり、どれが対象か書かれていない | TC 入力 (`TimecodePane.tsx` の `tcInput`) / nudge 8 個 (`ClipRangeView.tsx` の `stepRow`) / キーボード `←→` |
| B | nudge の**可視ラベルが同一** (`−10s −1s +1s +10s` が 2 組)。IN / OUT の区別は `aria-label` にしか無い | `ClipRangeView.tsx` の `stepRow` |
| C | 操作対象（active な端）が**枠色だけ**（cyan / gold） | `TimecodePane.module.css` の `.paneActive[data-pane]` |
| D | ペイン見出しが英語のみ（`IN (clip start)` / `OUT (clip end)`） | `ClipRangeView.tsx` の `TimecodePane label` |
| E | 変えた結果が読めない。`21.5 秒 (00:08:03 - 00:08:24)` だけで、**自動範囲との差**が無い。**自動に戻す手段も無い** | `ClipRangeView.tsx` の `duration` / `metadataStore.ts` の `setEventClipRange` |
| F | 端の時刻表示が 1 秒切り捨てなので、0.5 秒動かしても**数字が変わらないことがある** | `utils/time.ts` の `fmtClockTime` |
| G | 開いた直後、IN ペインの映像（イベントの瞬間）と TC（クリップ IN）が**食い違って見える** | `ClipRangeView.tsx` の `seekedToEventRef` effect |
| H | TC 入力にフォーカスしても**操作対象が切り替わらない**（`stopPropagation`）。OUT を編集した直後の `→` で IN が動く | `TimecodePane.tsx` の `tcInput onClick` |
| I | 遷移したことが caption でしか分からない（ペイン / nudge / KeyboardHints が境界エディタと同一） | `ClipRangeView.tsx` と `PreviewScreen.tsx` の描画比較 |
| J | 前後秒数 / 束ねは `ClipsScreen` の local state。preview へ行くと unmount され、戻ると既定（10 / 10 / 5）に戻る | `ClipsScreen.tsx` の `preText` 等 + `App.tsx` の条件描画 |
| K | 手動区間は試合区間へ**クランプされない**が、CLI は明示区間も試合区間へクランプし、潰れたら**クリップごと捨てる** | `ClipRangeView.tsx` の `applyStart`/`applyEnd` vs `clips.py` の `explicit` ループ |
| L | `[この範囲を保存]` は実は **metadata 全体**を永続化し、動画は生成しない | `metadataStore.ts` の `runApply` / `apply_changes` |
| M | sample mode（`filePath === null`）の扱いが無い。編集はできるが保存だけが無言で無効 | `ClipRangeView.tsx` に `isSample` 相当なし |
| N | TC の小数部は**フレーム番号**（60fps の `.20` = 0.333 秒）。秒の小数と誤読しうる | `TimecodePane.tsx` の `parseTimecode` / `utils/time.ts` の `fmtPreciseTime` |

## 2. デザインの狙い

> **開いた人が 3 秒で「この画面は何を決める場所か」「どの操作がどの端を動かすか」
> 「今どれだけ詰めたか」を読めるようにする。**

4 原則:

1. **作用点を名前で示す** — 端の区別を色に依存させない。IN / OUT を日本語で名指しし、
   どの操作がどちらに効くかを文字で書く（色は補助に降格）。
2. **操作と結果を分離する** — 1 行に混ざっていた「nudge ボタン + duration」を、
   「操作」ブロックと「結果」ブロックに分ける。
3. **基準を常に見せる** — 自動範囲と、そこからの差分を常時表示し、戻す手段を
   同じ場所に置く。
4. **表示＝実効（v2 追加）** — 画面に出した数値が、そのまま保存され、そのまま
   出力される。クランプ・設定共有・単位の食い違いで「表示と実効が違う」状態を作らない。

## 3. ゴール（判定可能）

| ID | ゴール | 判定方法 |
| --- | --- | --- |
| G1 | すべての nudge ボタンが、属する**行の見出し**で端を特定できる | 行見出し `IN (開始)` / `OUT (終了)` が各行の先頭に静的に存在する |
| G2 | 操作対象（`←→` が効く端）が**文字で**分かり、切り替え方も書いてある | 「操作対象: IN (開始)」相当の行 + 「ペインをクリックで切り替え」の 1 行 |
| G3 | ペイン見出しに日本語（開始 / 終了）が入る | 見出し文字列に `開始` / `終了` を含む |
| G4 | 自動範囲と差分が**常時**表示され（保存後も消えない）、`[自動範囲に戻す]` で戻せる | 結果ブロック 3 行 + 戻すボタンの状態。保存後も残る test |
| G5 | 0.1 秒の変化が表示に現れる | 端の時刻を 0.1 秒精度で表示（`HH:MM:SS.d`） |
| G6 | 画面の目的が上部 2 行で説明され、「試合の境界ではない」ことが書かれている | ヘッダの説明ブロック |
| G7 | 初見テスト: 「開始を 2 秒早めるにはどこを押すか」に 5 秒以内で答えられる | レビュアー（Kimi / Idios）の目視判定 |
| G8 | **表示した範囲がそのまま出力される**（試合区間クランプ・前後秒数・束ねを含む） | クランプの test / 設定共有の test / 束ね告知の表示 |
| G9 | **保存の意味が文言で分かる**（何を書き、動画は作らない） | 保存ボタン近傍の説明文 |

### 非ゴール

- **タイムライン上の帯ドラッグ**。工数が別次元なので別 issue 候補。
- **秒の専用数値入力**（`21.5` を直接打つ input）。TC 入力（フレーム精度）が既にある。
- **試合境界エディタ（`PreviewScreen`）の見た目・文言の変更**。`onFocus` の波及のみ。
- **キーボード割当の変更**（`←→` 1s / `Shift` 10s / `Alt` 1F / `Space` 再生）。

## 4. デザインモック

時刻の表示単位（v2 で統一）:

- TC（入力 / 編集）= `H:MM:SS.FF`。**`FF` はフレーム番号**（60fps なら `.12` = 0.2 秒）
- 結果ブロック = `HH:MM:SS.d`。**0.1 秒精度**
- 例: 0.2 秒は TC `.12` / 結果 `.2`。両方が同じ瞬間を指すようモックの数値を揃えてある

### S1: 自動範囲のまま（手動指定なし）

```text
  [◀ クリップ一覧へ]
  recording_20260116.mkv
  E:\royalstraightflesh\videos

  クリップ範囲 ⸱ CLIP RANGE
  KO の切り抜き範囲

  この画面は「この 1 本のクリップ」の開始 / 終了を決める画面です。試合の境界は変わりません。
  決めた範囲は metadata.json に保存され、allaganeye clips がその範囲で切り抜きます。

  ── 1  映像と操作対象  ⸱  VIEW ──────────────────────────────────────────────

  IN ⸱ 開始   ★操作対象                OUT ⸱ 終了
  +------------------------------+    +------------------------------+
  |          (video)             |    |          (video)             |
  |   [ 0:08:03.12         ]     |    |   [ 0:08:24.42         ]     |
  +------------------------------+    +------------------------------+

  ● 操作対象: IN (開始)   ←→ キーはこの端を動かします（ペインをクリックで切り替え）
  イベント発生 00:08:13.20

  ── 2  秒数の調整  ⸱  ADJUST ────────────────────────────────────────────────

  各ボタンは、その行の端だけを直接動かします（操作対象の選択は不要）。

  IN  (開始)   [ −10s ] [ −1s ] [ −0.1s ] [ +0.1s ] [ +1s ] [ +10s ]
  OUT (終了)   [ −10s ] [ −1s ] [ −0.1s ] [ +0.1s ] [ +1s ] [ +10s ]

  ← →  1 秒 ／ Shift + ← →  10 秒 ／ Alt + ← →  1 フレーム ／ Space  再生・停止
  ※ 上の TC は H:MM:SS.FF（FF = フレーム番号）。結果は 0.1 秒刻みで表示。
  ※ 無劣化 (copy) で切り抜くときは最寄りのキーフレームに丸まります（形式は一覧で選択）。

  ── 3  結果  ⸱  RESULT ──────────────────────────────────────────────────────

  クリップ   21.5 秒   00:08:03.2 → 00:08:24.7
  自動範囲   21.5 秒   00:08:03.2 → 00:08:24.7            自動範囲のまま

  [ このイベントの clip_start / clip_end を metadata.json に保存します。
    動画の切り抜きは [クリップ一覧] の [切り抜く] から実行します。 ]

  [ ⬦ この範囲を保存 ]                                [ 保存せず戻る ]
```

### S1b: 束ねられている場合（自動範囲が複数イベントの共通区間）

```text
  クリップ   41.0 秒   00:08:03.2 → 00:08:44.2
  自動範囲   41.0 秒   00:08:03.2 → 00:08:44.2            自動範囲のまま
             ↳ 近接 2 件の共通範囲。手動で保存するとこのイベントは分離されます。
```

### S2: 手動で変えた後（短くした例）

```text
  ── 3  結果  ⸱  RESULT ──────────────────────────────────────────────────────

  クリップ   19.5 秒   00:08:04.4 → 00:08:23.9            手動指定
  自動範囲   21.5 秒   00:08:03.2 → 00:08:24.7
  差         長さ −2.0 秒   （開始 +1.2 秒 ／ 終了 −0.8 秒）
  [ 自動範囲に戻す ]

  [ ⬦ この範囲を保存 ]        ● 未保存の変更        [ 保存せず戻る ]
```

> **差の符号規約**: 差は自動範囲に対する増減。`開始 +1.2` は「開始が後ろへ 1.2 秒」
> （クリップは短くなる）。`終了 −0.8` は「終了が前へ 0.8 秒」。

### S3: metadata に未保存のイベント（`position === null`）

```text
  このイベントは metadata.json に保存されていないため、範囲を保存できません。
  先に KO / ASSIST 検出を [適用] してください。

  （TC 入力 / nudge / 保存は無効。**再生は許可**（値を変えられないため）。
    自動範囲を引けないので、結果ブロックの「自動範囲」「差」「自動範囲に戻す」は出さない）
```

### S4: sample mode（`filePath === null`）

```text
  [サンプル動画では保存できません]   ← 既存 SampleModeBanner と同じ文言

  （TC 入力 / nudge / 保存をすべて無効。disabled の理由は DisabledTooltip で
    「サンプル動画では保存できません」。再生は許可）
```

### S5: 保存中 / 保存後 / 保存失敗

```text
  保存中      [ 保存中… ]（disabled）    ● 未保存の変更
  保存後      [ ⬦ この範囲を保存 ]       dirty が消え、結果ブロックは残る
               ┗ metadata.json にクリップ範囲を保存しました
               （自動範囲と一致した場合）┗ 自動範囲と同じため、手動上書きを削除しました
  保存失敗    [ ⬦ この範囲を保存 ]       エラー行（既存の applyErrorState）+ dirty と local 編集は残る
```

補足: 動的に出る文言は `role="status"` / `aria-live` を**新規に付けない**
（[`docs/a11y-policy.md`](../../a11y-policy.md)。既存の `clip-range-unlinked` の
`role="status"` は維持し、§10 の test で「この画面の live region はそれ 1 つだけ」を pin する）。

## 5. 部品仕様

| 要素 | 仕様 | 状態 / 備考 |
| --- | --- | --- |
| 主 caption | `クリップ範囲 ⸱ CLIP RANGE`（日本語先） | 常時。既存実装の語順を維持 |
| ヘッダ説明 | 2 行。①何を決める画面か ②試合の境界ではない + 保存先 + `allaganeye clips` が使う | 常時 |
| セクション見出し | `1  映像と操作対象 ⸱ VIEW` / `2  秒数の調整 ⸱ ADJUST` / `3  結果 ⸱ RESULT` | 常時。`候補フレーム ⸱ CANDIDATE FRAMES` と同じ caption idiom（区切りは U+3000 ではなく通常の空白 2 つ: `no-irregular-whitespace` 対応） |
| ペイン見出し | `IN ⸱ 開始` / `OUT ⸱ 終了` | **`IN` で始まる**ことを維持（`TimecodePane` の `paneKind` が `label.startsWith('IN')` で判定） |
| 操作対象の表示 | ペイン下の 1 行 `● 操作対象: IN (開始)  ←→ キーはこの端を動かします（ペインをクリックで切り替え）`（`clip-range-active-edge`）。ペイン見出しは `IN ⸱ 開始` / `OUT ⸱ 終了` | 色（cyan / gold）は補助として維持。**見出し横のバッジは実装しない**（共通部品 `TimecodePane` に badge prop を足さず、文字行だけで G2 を満たす） |
| イベント発生時刻 | `イベント発生 00:08:13.20` | 事実の表示のみ（初期映像位置の説明はしない） |
| nudge 行 | 2 行。行見出し `IN (開始)` / `OUT (終了)` + 6 ボタン `−10s −1s −0.1s +0.1s +1s +10s` + 冒頭に「各ボタンはその行の端だけを動かします」 | 行見出しで端を束縛。操作対象の選択は不要 |
| 単位の注記 | `※ 上の TC は H:MM:SS.FF（FF = フレーム番号）。結果は 0.1 秒刻みで表示。` | 常時（単位の読み違い防止） |
| copy 注記 | `※ 無劣化 (copy) で切り抜くときは最寄りのキーフレームに丸まります（形式は一覧で選択）。` | 常時。一覧の `clips-copy-note` の短縮版 |
| 結果: クリップ | `クリップ  N.N 秒  HH:MM:SS.d → HH:MM:SS.d` | 試合区間クランプ後の値（§7） |
| 結果: 自動範囲 | `自動範囲  N.N 秒  HH:MM:SS.d → HH:MM:SS.d` | `baseline` が引けるときだけ |
| 結果: 束ね告知 | `↳ 近接 N 件の共通範囲。手動で保存するとこのイベントは分離されます。` | `baseline.bundled > 1` のときだけ |
| 結果: 差 | `差  長さ ±N.N 秒 （開始 ±N.N 秒 ／ 終了 ±N.N 秒）` | 差が 0 のときは `自動範囲のまま` タグのみ |
| 手動タグ | `手動指定` | `events[position].clip_start` があるとき。既存 `clip-range-manual` の注記行は結果ブロックに統合して削除 |
| 保存の説明 | `このイベントの clip_start / clip_end を metadata.json に保存します。動画の切り抜きは [クリップ一覧] の [切り抜く] から実行します。` | 常時。**入場時に `dirty` が既に true** なら `他の未保存の変更も一緒に保存されます` を追加 |
| 自動範囲に戻す | secondary。押すと local を `baseline` に戻す。`[保存]` で `setEventClipRange(position, null)` | disabled = `baseline` 不明 **or** `isAtBaseline`（§7）。理由は `DisabledTooltip` |
| 保存 | `[⬦ この範囲を保存]`（既存）。成功時のみ注記を出す | 成功判定は store 状態（§7） |
| dirty 表示 | `● 未保存の変更`（既存） | `changed` の判定は維持 |

### 文言の差分（before → after）

| 位置 | before | after |
| --- | --- | --- |
| ペイン見出し | `IN (clip start)` / `OUT (clip end)` | `IN ⸱ 開始` / `OUT ⸱ 終了` |
| nudge 行 | 8 個が 1 行（区別なし） | 2 行 + 行見出し + 「行の端だけを動かす」1 行 |
| duration | `21.5 秒 (00:08:03 - 00:08:24)`（nudge 行の中央） | `クリップ 21.5 秒 00:08:03.2 → 00:08:24.7`（結果ブロック） |
| 手動注記 | `手動指定の範囲です（プレビューで保存済み）。` | 結果ブロックの `手動指定` タグ |
| 目的説明 | `IN / OUT がクリップの開始 / 終了です（試合の境界ではありません）。…` | §5 の 2 行 + 保存の説明 |

## 6. 情報の正

### D1: 前後秒数・束ねを session 設定へ移す（v2 追加）

`pre` / `post` / `gap` は baseline の定義に入る。`ClipsScreen` の local state のままだと

- 一覧で `pre=5` に変える → `[この範囲を確認]` → preview（`ClipsScreen` unmount）→ 戻ると 10/10/5
- その間に「自動範囲に戻す + 保存」すると、表示した baseline（pre=5）と実際に切り抜く範囲（pre=10）が食い違う

ので、`appStateStore.clipMargins = { pre, post, gap }` として保持し、
`ClipsScreen` の入力・baseline 計算・`start_clips` の引数・clip 一覧の表示が
**同じ値**を使う。既定は `DEFAULT_MARGIN_SECONDS` / `DEFAULT_GAP_SECONDS`。

副次効果: 現行の「一覧へ戻ると入力値が既定に戻る」挙動も解消する（意図した改善）。

### D2: `baseline` の定義と持ち方

「自動範囲」= **このイベントの上書きを消したときに `planClipWindows` が返す区間**。
イベント単体の `timestamp ± pre/post` ではなく、**束ね（`--gap`）と試合区間への
クランプを含む**ため、`planClipWindows` を通さないと正しくない。

```ts
clipRange: {
  start: number;
  end: number;
  matchIndex: number;
  position: number | null;
  /** v2: 「自動範囲に戻したときの区間」。引けない場合は null / 省略。 */
  baseline: { start: number; end: number; bundled: number } | null;
};
```

- `bundled` = その区間に束ねられたイベント数（1 は束ねなし）
- 作り方は呼び出し側（下記）。`baseline` が無いときは自動範囲 / 差 / 束ね告知 /
  戻すボタンを**出さない**（嘘の基準を出さない）
- 保存時は `{ ...clipRange, start, end }` で `baseline` / `matchIndex` / `position` を
  **保持する**（新しいオブジェクトを組み立て直さない）

| 呼び出し元 | baseline の作り方 |
| --- | --- |
| `ClipsScreen` | 対象イベントの `clip_start` / `clip_end` を消したクローンで `planClipWindows(events, matches, pre, post, gap)` を引き、対象 `position` の区間 + 同グループの件数 |
| `IndicatorsScreen` | 同関数を session 設定（既定 10 / 10 / 5）で引く |
| それ以外 | `baseline: null` |

### D3: 保存規則

1. local の `start` / `end` が `baseline` と一致（±0.005 秒）→ `setEventClipRange(position, null)`
   （上書きを残さない正規化）。成功注記は `自動範囲と同じため、手動上書きを削除しました`
2. それ以外 → `setEventClipRange(position, { start, end })`
3. どちらも保存後は `{ ...clipRange, start, end }` を積み、`baseline` を保持

## 7. 操作・状態機械

| 操作 | 遷移 | store mutation |
| --- | --- | --- |
| ペインの動画 / 空白をクリック | そのペインが操作対象 | なし（local `editing`） |
| TC 入力にフォーカス | そのペインが操作対象（`onFocus` → `onActivate`）。`stopPropagation` は維持 | なし |
| nudge ボタン | **その行の端だけ**を ± 秒。0.1 秒ステップは `Math.round(next * 10) / 10`、秒ステップは 0.001 秒丸め | なし（local） |
| `←→` / `Shift+←→` / `Alt+←→` | 操作対象の端を −/+ 1 秒 / 10 秒 / 1 フレーム。**TC 入力にフォーカス中は横取りしない**（既存挙動） | なし（local） |
| `Space` | 操作対象ペインの再生 / 停止（`position === null` でも許可） | なし |
| `[自動範囲に戻す]` | local を `baseline` に戻す（書き込みは `[保存]` まで行わない） | なし |
| `[⬦ この範囲を保存]` | §6 D3 の規則で書き込み → `apply()` | `metadataStore.setEventClipRange` + `apply()`、`appStateStore.setClipRange` |
| `[保存せず戻る]` / `[◀ クリップ一覧へ]` | `navigate('clips')` | なし |

### 制約（v2 で追加したものは ★）

- ★ **試合区間クランプ**: local の `start` / `end` は対象試合の `[start_time, end_time]` にも
  clamp する（`MAX(0, 試合開始)` / `MIN(試合終了)`）。CLI は明示区間も同じクランプをする
  ため（`clips.py`）、ここで揃えないと「表示した範囲」と「出力される範囲」が食い違う
- 開始は `終了 - 0.01` を越えない / 終了は `開始 + 0.01` を下回らない（既存）
- 非有限値は入力ごと捨てる（直前の有効値を保つ）
- ★ `position === null`: TC / nudge / 保存を無効（`editable = false`）。**再生は許可**
  （値を変える経路が無いため。現行実装も再生自体は止めていない）
- ★ **sample mode**（`filePath === null && metadata !== null`）: read-only。
  `SampleModeBanner` を表示し、TC / nudge / 保存を `DisabledTooltip`
  （`サンプル動画では保存できません`）で無効化。PreviewScreen と同じ choke point 方式
- `baseline` が引けないときは自動範囲系の表示・ボタンを出さない

### 保存の成否（★ v2 で明確化）

`apply()` は失敗を catch して `applyErrorState` / `conflictErrorState` に入れ、
**例外を投げずに resolve する**（`metadataStore.ts` の `runApply`）。したがって:

- 成功判定 = `await apply()` 後に `applyErrorState === null && conflictErrorState === null
  && dirty === false`
- 失敗時: 成功注記を出さず、`setClipRange` による `clipRange` 更新も行わない
  （local の編集値と dirty は残し、ユーザーが再試行できる）
- 成功注記は次の編集 / `[自動範囲に戻す]` / 次の保存開始で消す

## 8. 実装マッピング

| 変更先 | 内容 |
| --- | --- |
| `gui/src/screens/ClipRangeView.tsx` | レイアウト再構成（3 セクション）、ペイン label の日本語化（`IN ⸱ 開始`）、nudge 2 行化、結果ブロック、束ね告知、戻すボタン、試合区間クランプ、保存の正規化と成否判定、sample mode 対応、初期シークの変更（§11 R5） |
| `gui/src/screens/ClipRangeView.module.css` | セクション見出し / 行見出し / 結果ブロック / タグのスタイル追加（既存トークンのみ） |
| `gui/src/components/TimecodePane.tsx` | `onFocus` で `onActivate` を呼ぶ（**label は変更しない**。label は各呼び出し元の props） |
| `gui/src/state/appStateStore.ts` | `clipRange.baseline` を追加、`clipMargins {pre, post, gap}` を追加（reset でも初期化） |
| `gui/src/screens/ClipsScreen.tsx` | `preText` 等の実効値を `clipMargins` から読み、妥当な入力だけ store へ反映。`confirmRange` で `planClipBaseline` を計算して積む |
| `gui/src/screens/IndicatorsScreen.tsx` | `openEvent` で `planClipBaseline` を計算して積む |
| `gui/src/utils/time.ts` | `fmtClockTenths`（`HH:MM:SS.d`）を追加 |
| `gui/src/utils/clipWindow.ts` | `planClipWindowsDetailed`（束ね件数付き）と `planClipBaseline` を追加。`planClipWindows` は互換 wrapper |
| `docs/ui-interaction-spec.md` | §2.4.18 を本 note の確定内容に合わせて更新（§2.4.7 との差分を明記）、§2.8 の前後秒数入力の保持規則も更新 |

## 9. テスト観点

**`ClipRangeView`**

- 行見出し `IN (開始)` / `OUT (終了)` が存在し、各行のボタンがその端だけを動かす（既存 `aria-label` は維持）
- `★操作対象` / `● 操作対象: …` が `editing` に追従する
- TC 入力のフォーカスで操作対象が切り替わり、**blur 後**の `→` がその端を動かす（INPUT 内 Arrow を奪わない既存 test は維持）
- 結果ブロック: 自動（`自動範囲のまま`）/ 手動（`手動指定` + 差の 3 値）/ 差の符号規約
- 束ね時: `近接 N 件の共通範囲` の告知が出る / `bundled === 1` では出ない
- `[自動範囲に戻す]` が local を baseline に戻し、`[保存]` で `clip_start` / `clip_end` が消える
- **`isAtBaseline` が local 比較**であること: 「保存済みは自動 + local だけ変更」で戻すが有効
- local が baseline と一致する保存で `null` を書く（正規化）
- **保存後も結果ブロックが残る**（`baseline` 保持の regression）
- **保存失敗時**: 成功注記が出ない / `clipRange` と dirty が残る / エラー行が出る
- **試合区間クランプ**: 試合開始ちょうど / 開始より前 / 終了より後 への操作が clamp される
- `baseline` 未設定で自動範囲系が出ない
- `position === null`: TC / nudge / 保存が無効、**再生は可能**
- sample mode: TC / nudge / 保存が無効 + 理由が出る
- 0.1 秒ステップの丸め（`21.5 + 0.1` の累積誤差が保存値に出ない）
- **live region**: 画面内の `[role="status"], [role="alert"], [aria-live]` が
  `clip-range-unlinked` の 1 つだけであることを DOM query で pin
  （jest-axe は live region の新規追加を検出できない）

**呼び出し元 / 共通**

- `ClipsScreen`: baseline を積む / 非既定の pre・post・gap で開いても、一覧に戻ったときの
  表示区間と baseline が同じ値を使う（session 設定の共有）
- `IndicatorsScreen`: baseline を積む
- `appStateStore`: `clipMargins` が reset で初期化される
- `PreviewScreen`: `onFocus` 追加による回帰がないこと（既存 test が green のまま）
- `fmtClockTenths` の単体（0 / 1 秒未満 / 1 時間以上）

## 10. 規約チェック

- **a11y**: 新規の `role="status"` / `role="alert"` / `aria-live` を追加しない。
  操作対象は**文字**で示す。disabled には `DisabledTooltip` で理由
  （`docs/ui-interaction-spec.md` §1.2）。**live region の集合は §9 の DOM query で pin する**
  （jest-axe 緑は根拠にならない）
- **scope**: `PreviewScreen` の見た目・文言は変えない（`TimecodePane` の `onFocus` のみ波及）
- **壊さない**: `clip_start` / `clip_end` の書込条件、`apply()` の atomic write、
  `pendingSeekSeconds` の消費、`position === null` の無効化は既存挙動を維持
  （ただし §11 R5 で初期シークの要件を変更する）
- **docs**: `docs/ui-interaction-spec.md` §2.4.18 / §2.8 を同時更新

## 11. 決定事項（v2 で確定）

| ID | 論点 | 決定 | 根拠 / 変更点 |
| --- | --- | --- | --- |
| R1 | `±0.1s` ボタン | **入れる** | マウス利用者に「秒」で操作させる。`copy` の丸めは同じ画面に注記。レビューも推奨 |
| R2 | baseline 一致時の上書き削除 | **採用** | ただし成功注記を「自動範囲と同じため、手動上書きを削除しました」にする（レビュー指摘） |
| R3 | TC フォーカスで操作対象を切り替える | **採用** | `TimecodePane` に `onFocus` を追加。test は blur 後に行う（レビュー指摘 10）。PreviewScreen の回帰 test も追加 |
| R4 | 束ね表示 | **出す（v2 で変更）** | 当初は「出さない」としたが、手動保存すると**そのイベントが束ねから外れ、残りのイベントの区間・クリップ番号も変わる**ため、副作用の説明として必要（レビュー指摘 4） |
| R5 | 初期の IN 映像位置 | **クリップ IN に合わせる（v2 で変更）** | 映像と TC の不一致（症状 G）は説明文では解消しない。イベント発生時刻は静的表示として残す。**#1139 の「初期シークはイベント開始」を本 issue で要件変更する**（下記） |
| R6 | 保存後の遷移 | **留まる** | 成功注記は `metadata.json にクリップ範囲を保存しました`、次の編集で消す |
| R7 | 置き場 | **#1156（本 issue）/ 別 PR** | 決定済み |

### R5 の要件変更（#1139 の AC 更新）

- **旧**: 一覧の行から開いたら IN ペインを**イベントの発生時刻**へシークする
- **新**: IN ペインは**クリップ IN**（= 編集 TC と同じ時刻）へシークする。
  イベントの発生時刻は `イベント発生 hh:mm:ss` の静的な表示だけ残す
- **理由**: 映像と TC が別の時刻を指す状態は、説明を足しても解消しない（レビュー指摘）。
  この画面の目的は「範囲を決める」ことであり、KO の瞬間は再生 / スクラブで見られる

## 12. 影響範囲・リスク

| リスク | 対策 |
| --- | --- |
| `TimecodePane` の `onFocus` が試合境界エディタに波及する | 追加は focus 時の `onActivate` のみ。`PreviewScreen.test.tsx` の既存 test で回帰確認 |
| `pre` / `post` / `gap` の store 移設で `ClipsScreen` の挙動が変わる | 入力値が画面遷移で保持される（改善）。`ClipsScreen.test.tsx` に保持の test を追加 |
| 試合区間クランプで「これ以上伸ばせない」状態が増える | クランプ後も値は変わる（開始 / 終了の限界で停止）。`範囲外` になる組は一覧側の既存表示に従う |
| `baseline` の計算が呼び出し側 2 箇所に増える | `planClipWindows` は pure。`ClipsScreen` は既に同関数を呼んでいる |
| 0.1 秒ステップで保存値の精度が荒れる | 丸め規則を §7 に固定し test で pin |
| 画面の情報量が増えて逆に読みにくくなる | セクション 3 つ + 結果 4 行 + 注記 2 行に上限。増やすときは本 note を更新してから |

## 13. v2 changelog（2026-11-24 レビュー反映）

| レビュー指摘 | 反映先 |
| --- | --- |
| 1 (High) 前後秒数が画面遷移で失われ baseline が食い違う | §0 スコープ追加 / §6 D1 / §8 / §9 |
| 2 (High) 保存で `baseline` が消える | §6 D2 D3 / §7 / §9 |
| 3 (High) TC の `.FF` はフレーム番号 | §4 の単位規約とモック / §5 / §9 |
| 4 (High) 束ねからの分離の副作用 | §4 S1b / §5 / §11 R4 変更 |
| 5 (High) 手動区間が試合区間へクランプされない | §7 制約 / §9 / G8 |
| 6 (High) 保存対象の説明が狭い | §5 保存の説明 / §4 S1 / §7 |
| 7 (Medium) S1 / S2 の数値と dirty の不整合 | §4 S1 / S2 / 符号規約 |
| 8 (Medium) 戻すボタンの disabled 条件が曖昧 | §5 / §7 `isAtBaseline` |
| 9 (Medium) `apply()` は失敗を握る | §7 保存の成否 / §9 |
| 10 (Medium) R3 の test が成立しない | §9 / §11 R3 |
| 11 (Medium) 全無効化の対象と sample mode が未定義 | §4 S3 S4 / §7 |
| 12 (Medium) pin 不足と jest-axe では live region を検出できない | §9 / §10 |
| 13 (Low) セクション 1→2 の操作モデルが不明 | §4 S1 / §5 |
| 14 (Low) caption の語順 / label の変更先 | §5 / §8 |

## 14. 実装メモ (2026-11-24)

実装で確定した差分。設計文書を読むときは本節を先に見る。

| 項目 | 設計 | 実装 |
| --- | --- | --- |
| 操作対象の表示 | ペイン見出し横に `★操作対象` + ペイン下の 1 行 | **1 行だけ**（`clip-range-active-edge`）。共通部品 `TimecodePane` に badge prop を足さないため |
| セクション区切り | `1  映像と操作対象` | 区切りは **通常の空白 2 つ**（U+3000 は `no-irregular-whitespace` で lint error） |
| 束ね件数 | `planClipWindows` の戻り値に含める案 | `planClipWindowsDetailed`（`{windows, bundled}`）+ 互換 wrapper `planClipWindows` と、`planClipBaseline(events, matches, pre, post, gap, position)` |
| 「他の未保存の変更」注記 | 入場時に `dirty` なら出す | `useState` の遅延初期化で入場時の `dirty` を 1 回だけ捕捉（`react-hooks/refs` は render 中の ref 参照を禁止するため） |
| 結果の丸め | 0.1 秒精度で表示 | `fmtClockTenths` は **四捨五入**（切り捨てだと 0.5 秒動かしても表示が変わらない） |
| 編集値の丸め | — | ローカル値は 1e-4 秒に丸める（0.1 秒ステップの累積誤差を保存値に残さない） |
| スクショ | 描画変更があれば再撮影 | 8 枚とも描画変更なし（`ClipRangeView` は撮影対象外、`ClipsScreen` は初期値 10/10/5 で同一）。画像は revert し `sources_sha256` のみ更新 |
