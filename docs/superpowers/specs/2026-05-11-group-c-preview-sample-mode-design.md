# Lane II-a / Group C — PreviewScreen / sample mode UX 系 design

> **Status**: brainstorming complete (2026-05-11)
> **作成**: 2026-05-11 / session `cranky-sanderson-2872af`
> **対象 issue**: [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) (P2) / [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) (P3) / [#677](https://github.com/Idios/kobutachan-allaganeye/issues/677) (P3 bug)
> **roadmap 位置**: [Lane II-a (Group C)](../plans/2026-05-11-l2-v020-roadmap-update.md) §2 Group C — Wave 1
> **PR 戦略**: 3 PR (1 issue = 1 PR、Iron Law 3 canonical)
> **PR 順序**: #633 → #645 → #677

## 1. Overview

Group C は PreviewScreen 周辺の UX 系 3 issue を直列消化する単位。共通点は「PreviewScreen を中心とした GUI の対話品質」だが、内部的には独立した 3 chapter で構成される:

- **Chapter 1 (#633)**: sample mode 全画面 read-only 化 — Complete / Preview / Export 3 画面 + 共通 banner + tooltip
- **Chapter 2 (#645)**: preview 微細タイムライン (±5s) — 新 Tauri command + 新 component
- **Chapter 3 (#677)**: SideRail 全体削除 — App.tsx 改修 + 5 画面レイアウト回帰

直列順は roadmap §2 の指定通り (#633 排他ガード先行 → #645 編集 UX 拡張 → #677 独立 UI 整理)。各 chapter は別 PR (1 PR = 1 issue、Iron Law 3 准拠)。

### 1.1 採用方針サマリ (brainstorming Q1-Q7)

| # | 質問 | 採用 | 根拠 |
| --- | --- | --- | --- |
| Q1 | PR 分割戦略 | 3 PR (canonical) | Iron Law 3「1 PR = 1 章 (= 1 issue) 原則」 |
| Q2 | SampleModeBanner 配置 | Per-screen | 各画面 opt-in、レイアウト共通層への knowledge リーク回避 |
| Q3 | Disabled UI 密度 | §1.2 strict | 既存 DisabledTooltip / RestoreButton pattern と一貫、§1.2 spec 一致 |
| Q4 | brightness data source | Tauri command on-demand | metadata.brightness_samples 最大 512 点では ±5s 不足。FrameStrip thumbnail と同 pattern |
| Q5 | MicroTimeline 実装方針 | 新 component + utils 共有 | scope 最小、BrightnessTimeline 不変で regression risk 抑制 |
| Q6 | MicroTimeline UX | Display-only / FrameStrip 直上 | P3 priority 適合、interactive 化は派生 issue |
| Q7 | SideRail 削除粒度 | (b) 全体削除 | ユーザー希望「ボタンを一旦削除」、ALLAGAN identity は AllaganCorner / AllaganFrame で代替 |

## 2. Chapter 1 (#633) sample mode 全画面 read-only 化

**対象 PR**: PR 1 本目 (P2、Group C 先頭)
**対象 issue**: [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633)
**派生元**: [#589](https://github.com/Idios/kobutachan-allaganeye/issues/589) (silent edit loss bug、partial close 後継)

### 2.1 新規 component: `SampleModeBanner.tsx`

```text
gui/src/components/
├── SampleModeBanner.tsx       (新規、~30 行)
└── SampleModeBanner.module.css (新規、~20 行)
```

**API** (props なし、store 直接 subscribe で各画面で同じ判定):

```tsx
export function SampleModeBanner() {
  const isSample = useMetadataStore(
    (s) => s.filePath === null && s.metadata !== null,
  );
  if (!isSample) return null;
  return (
    <div className={styles.banner} role="status" aria-live="polite">
      サンプル動画です。実際の動画を選択すると保存できます。
    </div>
  );
}
```

判定式 `filePath === null && metadata !== null` で「sample mode (`loadSample()` 経由)」と「初期 idle (`metadata === null`)」を区別する。後者は banner 出さない (DropScreen で metadata 未ロードのため)。

`metadataStore.filePath` / `loadSample()` は既存 ([gui/src/state/metadataStore.ts:28, 130](../../gui/src/state/metadataStore.ts))。

**配置** (Q2 = per-screen banner): 各画面の `<div className={styles.screen}>` 直下、`header` 直前。

- [gui/src/screens/CompleteScreen.tsx](../../gui/src/screens/CompleteScreen.tsx)
- [gui/src/screens/PreviewScreen.tsx](../../gui/src/screens/PreviewScreen.tsx)
- [gui/src/screens/ExportScreen.tsx](../../gui/src/screens/ExportScreen.tsx)

DropScreen / DetectingScreen は `metadata === null` のため banner 自然に非表示 (条件式で短絡)。

**styling**: `--ae-gold-dim` 背景 + `--ae-bg` テキスト、上下 8px / 横 16px padding、border-bottom 1px gold。`role="status" aria-live="polite"` で screen reader 読み上げ。

### 2.2 disabled 適用 (Q3 = §1.2 strict)

各 disabled control は既存 [`DisabledTooltip`](../../gui/src/components/DisabledTooltip.tsx) を wrap 経由で適用。tooltip 単独 (副次) と inline hint 併用 (主要 CTA) を §1.2 仕様通り使い分ける。

#### 2.2.1 PreviewScreen 編集系部品 (tooltip のみ)

| 部品 | sample mode で disabled | reason 文字列 |
| --- | --- | --- |
| matchName input | ✓ | `'サンプル動画では保存できません'` |
| matchType select | ✓ | 同上 |
| Pane.tcInput (×2 IN/OUT) | ✓ | 同上 |
| stepRow buttons ×6 (-10s/-1s/-1f/+1f/+1s/+10s) | ✓ | 同上 |
| FrameStrip onSelectFrame (各 frame click) | ✓ | 同上 |

#### 2.2.2 PreviewScreen 主要 CTA (tooltip + inline hint)

| 部品 | reason 優先順 |
| --- | --- |
| [適用] button | `applying ? '適用中…' : isSample ? 'サンプル動画では保存できません' : ''` |
| [元に戻す] (RestoreButton) | `restoring ? '復元中です' : isSample ? 'サンプル動画では保存できません' : !hasBackup ? 'バックアップが存在しません' : ''` |
| [書き出し] (画面下部) | `isSample ? 'サンプル動画では保存できません' : ''` |

`DisabledTooltip` は `inlineHint={true}` で渡す。

#### 2.2.3 ExportScreen 主要 controls (tooltip + inline hint、issue body 指定)

| 部品 | reason 文字列 |
| --- | --- |
| [⬦ 書き出し開始] | `'サンプル動画では保存できません'` |
| 出力先 input | 同上 |
| 命名規則 input | 同上 |
| コーデック selector ×2 | 同上 |
| per-match exclude checkbox (各 row) | 同上 |
| [全選択] / [全解除] | 同上 |

#### 2.2.4 CompleteScreen

- [元に戻す] (RestoreButton): 2.2.2 と同じ reason 切替 (RestoreButton は 2 画面共有のため `RestoreButton.tsx` 内で sample 判定)
- 編集系部品なし (list view のみ)、追加 disabled なし

### 2.3 RestoreButton 改修

[gui/src/components/RestoreButton.tsx:65-69](../../gui/src/components/RestoreButton.tsx#L65) の `reason` ロジックを sample mode 優先に拡張:

```tsx
const isSample = useMetadataStore(
  (s) => s.filePath === null && s.metadata !== null,
);
const disabled = !hasBackup || restoring || isSample;
const reason = restoring
  ? '復元中です'
  : isSample
    ? 'サンプル動画では保存できません'
    : !hasBackup
      ? 'バックアップが存在しません'
      : '';
```

§1.2 主要 CTA 規約により inline hint も付ける (`inlineHint={true}` 化、現状 false)。

### 2.4 doc 整合 (`docs/ui-interaction-spec.md`)

- §1.2 アンチパターン例「派生 issue で対応予定」記述削除
- §1.4 表「派生 issue で対応予定」記述削除
- §2.3 (complete) に RestoreButton sample mode reason canonical 追記
- §2.4 (preview) [適用] / [元に戻す] / 編集系部品の sample mode reason 追記
- §2.5 (export) 各 disabled CTA の sample mode reason 追記
- 「現状未実装」「§1.4 違反」「§1.2 違反」注記すべて解消

### 2.5 vitest

#### 2.5.1 新規 test

- `gui/src/components/SampleModeBanner.test.tsx`:
  - sample mode (`loadSample()` 後) で banner mount
  - 通常 file (`load(path)` 後) で banner 非表示
  - 初期 idle (`metadata === null`) で banner 非表示
  - text content + `role="status"` + `aria-live="polite"` assertion

#### 2.5.2 既存 test 拡張

- `CompleteScreen.test.tsx`: sample mode で SampleModeBanner mount + RestoreButton tooltip reason ('サンプル動画では…') + inline hint
- `PreviewScreen.test.tsx`: sample mode で各編集系部品 disabled 状態 + tooltip reason + 主要 CTA inline hint
- `ExportScreen.test.tsx`: sample mode で各 disabled CTA tooltip + inline + bulk button

### 2.6 受け入れ条件 (#633 issue body 逐条)

| # | issue body 項目 | 対応箇所 |
| --- | --- | --- |
| 1 | 3 画面の上部 inline banner (共通 component 化検討) | §2.1 SampleModeBanner |
| 2 | preview 編集系部品 disabled (matchName / matchType / Pane.tcInput / stepRow ×6 / FrameStrip onSelectFrame) | §2.2.1 |
| 3 | export 主要 controls disabled (8 部品) | §2.2.3 |
| 4 | complete RestoreButton (既存対応 + tooltip) | §2.2.4 / §2.3 |
| 5 | 各 disabled に inline hint「サンプル動画では保存できません」 | §2.2.2 (主要 CTA inline) + §2.1 banner で代替 (副次は §1.2 strict 採用、tooltip のみ) |
| 6 | RestoreButton tooltip (hasBackup=false / restoring=true) | §2.3 |
| 7 | preview [適用] tooltip (applying / sample mode) | §2.2.2 |
| 8 | export 各 disabled CTA tooltip | §2.2.3 |
| 9 | vitest (3 画面 banner / disabled / RestoreButton tooltip) | §2.5 |
| 10 | doc 注記解消 (ui-interaction-spec §2.3 / §2.4 / §2.5 / §1.2 / §1.4) | §2.4 |

**AC #5 解釈の明示**: issue body は「各 disabled に inline hint」と書くが、§1.2 spec は「副次 UI は tooltip 単独 / 主要 CTA のみ tooltip+inline 併用」を canonical 規定。本 spec は §1.2 strict 解釈 (§2.2 表通り) を採用し、inline hint は banner (上部) + 主要 CTA 周辺のみ配置する。副次部品 (input / select / step button) は tooltip のみ。重複情報を最小化しつつ「壊れた / 仕様か」混乱は banner で解消する。spec として §1.2 を上位規約と扱う旨を本節に明記。

### 2.7 実機検証 trigger (Iron Law 6)

PR #633 マージ前に Idios に実機検証依頼:

- Tauri 起動 (`cd gui && npm run tauri dev`) で sample mode (StateSwitcher 経由) → Complete / Preview / Export 各画面で:
  - 上部 banner 表示
  - 各 disabled control の hover で tooltip
  - 主要 CTA の inline hint 可視
- 実 file 選択経路で banner 非表示確認
- DropScreen / DetectingScreen で banner 非表示確認

`AskUserQuestion` で Idios に依頼する。mock テスト pass = 実機検証不要 は Iron Law 6 Red Flag。

## 3. Chapter 2 (#645) preview 微細タイムライン (±5s)

**対象 PR**: PR 2 本目 (P3、Chapter 1 merge 後)
**対象 issue**: [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645)
**派生元**: [#465](https://github.com/Idios/kobutachan-allaganeye/issues/465) (close 時に検出した未消化作業)

### 3.1 新規 Tauri command: `extract_brightness_window`

[gui/src-tauri/src/lib.rs](../../gui/src-tauri/src/lib.rs) に追加。

**Rust signature**:

```rust
#[tauri::command]
async fn extract_brightness_window(
    video_path: String,
    t_start: f64,         // 秒 (絶対時刻、例: match boundary - 5.0)
    t_end: f64,           // 秒 (例: match boundary + 5.0)
    fps: f64,             // サンプリング fps (default 10.0、=100 sample/10s)
) -> Result<BrightnessWindow, AppError>;

#[derive(serde::Serialize, ts_rs::TS)]
pub struct BrightnessWindow {
    pub samples: Vec<f64>,    // 0.0〜255.0 (フレーム平均輝度)
    pub t_start: f64,         // echoed
    pub t_end: f64,           // echoed
    pub fps: f64,             // echoed
}
```

**実装方針**:

- 既存 [`generate_match_thumbnails`](../../gui/src-tauri/src/lib.rs) と同経路で ffmpeg spawn:
  - `ffmpeg -ss {t_start} -i {video_path} -t {t_end-t_start} -vf "fps={fps},scale=320:180,format=gray" -f rawvideo -`
- stdout から raw frame bytes を読み (320×180 = 57600 bytes/frame、`format=gray` で 1 byte/pixel)、各フレームの平均輝度を `bytes.iter().map(|b| *b as f64).sum::<f64>() / 57600.0` で計算
- AppError 経路 ([Group A #663](https://github.com/Idios/kobutachan-allaganeye/pull/689) 確立済) に乗せ、`error.rs::default_hint_for_code` 既存 entry (`ffmpeg.spawn_failed` / `ffmpeg.exit_nonzero`) を再利用
- timeout: 5 秒 (10s window × 10fps = 100 frame、CPU でも ~200ms 想定、余裕を持って 5s)
- ffmpeg 終了は `wait_with_output()` で同期待ち (`run_in_background` 不使用、`feedback_taskstop_child_process_leak.md` 参照)

**呼び出し元**: [gui/src/screens/PreviewScreen.tsx](../../gui/src/screens/PreviewScreen.tsx) の selectedMatch 変更 `useEffect` 内 (§3.3)。

### 3.2 新規 component: `MicroTimeline.tsx`

```text
gui/src/components/
├── MicroTimeline.tsx       (新規、~80 行)
└── MicroTimeline.module.css (新規、~30 行)
```

**API**:

```tsx
export interface MicroTimelineProps {
  samples: readonly number[];   // 0〜255 (BrightnessWindow.samples)
  windowSeconds: number;        // ±5s なら 10
  threshold: number;            // detection_params.blackout_threshold (default 15)
  // 表示専用、interaction なし (Q6 = display-only)
}
```

**SVG 構成** (BrightnessTimeline と類似だが axis ラベルと boundary marker が異なる):

- viewBox: 200×40 (FrameStrip 幅整合のコンパクト高さ)
- threshold line (`y = H - threshold/255 * H`、--ae-danger 系の点線)
- blackout band (`findBlackoutRegions(samples, windowSeconds, threshold)` 共有 utility 経由、--ae-cyan 半透明)
- waveform path (`buildBrightnessPath` 共有 utility 経由、--ae-gold 1px line)
- **boundary marker** (中央 vertical 白破線): `x1=W/2 x2=W/2 y1=0 y2=H stroke="white" stroke-dasharray="1,1"`
- 軸 (`-5s` / `0` / `+5s`): 3 tick label (BrightnessTimeline は 0/25/50/75/100% の 5 tick で別物)

共有 utility ([`gui/src/utils/brightness.ts`](../../gui/src/utils/brightness.ts)) はそのまま再利用。BrightnessTimeline は不変 (regression risk 最小化)。

### 3.3 PreviewScreen 統合

**配置** (Q6 = A、FrameStrip caption 直上): `<div className={styles.strip}>` 内、既存 `stripCaption` の前に新 section 挿入。

```tsx
<div className={styles.strip}>
  <div className={styles.stripCaption}>微細タイムライン ⸱ ±5s</div>
  {brightnessWindow ? (
    <MicroTimeline
      samples={brightnessWindow.samples}
      windowSeconds={10}
      threshold={detectionParams.blackout_threshold}
    />
  ) : microError ? (
    <div className={styles.microError} role="alert">
      <span>{appErrorMessage(microError)}</span>
      {appErrorHint(microError) && (
        <span className={styles.microErrorHint}>💡 {appErrorHint(microError)}</span>
      )}
    </div>
  ) : (
    <div className={styles.microTimelineLoading}>計測中…</div>
  )}
  <div className={styles.stripCaption}>候補フレーム ⸱ CANDIDATE FRAMES</div>
  <FrameStrip ... />
</div>
```

**state 管理** (PreviewScreen 内 local state、metadataStore に持たせない):

```tsx
const [brightnessWindow, setBrightnessWindow] = useState<BrightnessWindow | null>(null);
const [microError, setMicroError] = useState<AppError | null>(null);

useEffect(() => {
  if (!selectedMatch || !filePath) {
    setBrightnessWindow(null);
    setMicroError(null);
    return;
  }
  setBrightnessWindow(null);
  setMicroError(null);
  invoke<BrightnessWindow>('extract_brightness_window', {
    videoPath: filePath,
    tStart: Math.max(0, selectedMatch.start_time - 5.0),
    tEnd: selectedMatch.start_time + 5.0,
    fps: 10.0,
  })
    .then(setBrightnessWindow)
    .catch((e) => setMicroError(toAppError(e)));
}, [selectedMatch?.index, filePath]);
```

`Math.max(0, ...)` で動画開始端の clamp。動画末端の clamp は `selectedMatch.start_time + 5.0` が duration を超えても ffmpeg 側で短く返るため Rust 側 (= ffmpeg) に委譲。

### 3.4 sample mode の扱い

sample mode (`filePath === null`) では Tauri command 不可。判断 (default 採用):

- **採用 (ii) synthetic data**: 既存 [`buildLocalBrightness`](../../gui/src/utils/brightness.ts#L86) を用いて synthetic 波形を表示。caption に「サンプル波形」hint を 1 行付ける。
- 理由: UI 学習価値 (空表示より MicroTimeline の見た目が伝わる)、`buildLocalBrightness` が既に synthetic 用に設計済 (placeholder からの正規化路)

実装:

```tsx
const isSample = useMetadataStore((s) => s.filePath === null && s.metadata !== null);

useEffect(() => {
  if (!selectedMatch) { /* ... */ return; }
  if (isSample) {
    // sample mode: synthetic
    setBrightnessWindow({
      samples: buildLocalBrightness(selectedMatch.start_time, 5, 10),
      t_start: selectedMatch.start_time - 5,
      t_end: selectedMatch.start_time + 5,
      fps: 10,
    });
    return;
  }
  // real file: invoke
  /* ... 上記 */
}, [selectedMatch?.index, filePath, isSample]);
```

stripCaption を sample 時は「微細タイムライン ⸱ ±5s ⸱ サンプル波形」に変える。

### 3.5 vitest

#### 3.5.1 新規 test

- `gui/src/components/MicroTimeline.test.tsx`:
  - mount + threshold line 描画 (y 座標 calculation 確認)
  - blackout band 描画 (samples 中の 15 未満区間)
  - boundary marker (`x = viewBox.width/2`)
  - axis labels (-5s / 0 / +5s)
  - waveform path (samples → SVG path)

#### 3.5.2 既存 test 拡張

- `PreviewScreen.test.tsx`:
  - selectedMatch 変更時に `extract_brightness_window` invoke される (mock)
  - 取得成功で MicroTimeline render
  - 取得失敗で inline error (`appErrorMessage` + `appErrorHint`)
  - sample mode で `buildLocalBrightness` の synthetic を render + sample caption

#### 3.5.3 Rust side test

- `extract_brightness_window` の integration test (実 ffmpeg call、`ALLAGANEYE_AUDIO_TEST_VIDEO` の primary 録画使用、`#[ignore]` で slow marker 相当)
- ffmpeg 1秒インターバル必須 (`feedback_ffmpeg_test_interval.md` 参照)

### 3.6 doc

- `docs/ui-interaction-spec.md` §2.4 (preview) に新部品セクション `§2.4.X MicroTimeline (±5s 微細タイムライン)` を追加: 種類 / 状態 (loading / loaded / error / sample) / 遷移トリガー / store mutation (なし、local state) / 例外 (microError は §1.5 inline error)
- `docs/tauri-commands.md` に `extract_brightness_window` 追加 (Group J #692 hint table drift check 対象になる前提で error code mapping 整合を spec 段階で担保)
- `docs/metadata-spec.md` 不変 (metadata.json schema 拡張なし)

### 3.7 受け入れ条件 (#645 issue body 逐条)

| # | issue body 項目 | 対応箇所 |
| --- | --- | --- |
| 1 | preview 画面 FrameStrip 周辺に微細タイムライン UI 部品を配置 | §3.3 (FrameStrip 直上) |
| 2 | 輝度波形データ取得経路の検討 (CSV vs ffmpeg subprocess) | §3.1 (Tauri command on-demand 採用、Q4 確定) |
| 3 | 閾値線 (`detection_params.blackout_threshold`) を CompleteScreen と同じスタイルで描画 | §3.2 (共有 utility + threshold line) |
| 4 | 検知済 blackout region (試合境界中心 ±5s 範囲) をマーカーで強調 | §3.2 (`findBlackoutRegions` 共有 utility 経由で blackout band) |
| 5 | vitest (部品 mount / 閾値線 / マーカー描画) | §3.5 |
| 6 | docs/ui-interaction-spec.md §2.4 (preview) に微細タイムラインの UI 部品状態機械追加 | §3.6 |

### 3.8 実機検証 trigger (Iron Law 6)

PR #645 マージ前に Idios に実機検証依頼:

- 実動画 (`ALLAGANEYE_SAMPLE_VIDEO_DIR`) で Preview 開く
  - MicroTimeline が ~200ms で描画
  - 試合切替で再取得 (loading → loaded 遷移)
  - 取得失敗 (動画削除等) で inline error 表示
- sample mode (StateSwitcher) で synthetic 波形 + 「サンプル波形」caption 確認
- ffmpeg 8.1 PTS offset (#575) で表示位置に違和感ないこと (±~1.1s 想定範囲内)

## 4. Chapter 3 (#677) SideRail 全体削除

**対象 PR**: PR 3 本目 (P3 bug、独立)
**対象 issue**: [#677](https://github.com/Idios/kobutachan-allaganeye/issues/677)
**ユーザー希望**: 「ボタンを一旦削除」 → Q7 で (b) SideRail 全体削除を確定

### 4.1 削除対象 file

```text
gui/src/components/
├── SideRail.tsx              ← 削除
├── SideRail.module.css       ← 削除
└── SideRail.test.tsx         ← 削除 (存在する場合、章執筆時に find で確認)
```

### 4.2 App.tsx 改修

[gui/src/App.tsx](../../gui/src/App.tsx) から SideRail import + render を削除:

```tsx
// before
import { SideRail } from './components/SideRail';
// ...
<div className={styles.shell}>
  <SideRail />
  <main className={styles.main}>{/* ... */}</main>
  {/* StateSwitcher */}
</div>

// after
<div className={styles.shell}>
  <main className={styles.main}>{/* ... */}</main>
  {/* StateSwitcher */}
</div>
```

`App.module.css` の `.shell` flex layout (`flex-direction: row`) は維持 (StateSwitcher の右上 absolute 配置との整合)。SideRail 関連 selector (border-right 等) があれば cleanup。

### 4.3 layout 回帰確認

SideRail 削除で main content 幅が +48px される。5 画面全レイアウト visual 回帰の実機検証必要 (§4.7)。

ALLAGAN identity は [`AllaganCorner`](../../gui/src/components/AllaganCorner.tsx) (右上 ◈ アクセント) と [`AllaganFrame`](../../gui/src/components/AllaganFrame.tsx) (画面 frame) で継続維持される。SideRail 削除による identity 損失は最小化。

### 4.4 vitest

- `SideRail.test.tsx` 削除
- `App.test.tsx` (存在すれば): SideRail render assertion を削除
- 5 screen test に SideRail mention あれば削除 (`find gui/src -name "*.test.tsx" -exec grep -l "SideRail" {} \;` で要洗い出し、章執筆時に実施)
- jest-axe 違反が新規発生しないこと (#587 の existing a11y test pattern を 5 画面巡回確認)

### 4.5 design doc 整合

- [docs/design/bundle/project/variants/aether.jsx](../../docs/design/bundle/project/variants/aether.jsx) lines 438-453 の inline rail mock との乖離 → comment 追記:

  ```jsx
  // [2026-05-11 #677] inline rail removed in production (icons looked
  // selectable but had no nav function). aether.jsx kept as historical
  // mockup; SideRail.tsx component deleted in PR for #677.
  ```

- [docs/design/README.md](../../docs/design/README.md) / [docs/ui-architecture.md](../../docs/ui-architecture.md) に SideRail 記述があれば削除 / 更新 (章執筆時 grep)

### 4.6 受け入れ条件 (#677 issue body 逐条)

| # | issue body 項目 | 対応箇所 |
| --- | --- | --- |
| 1 | 4 つのアイコン (◈ ◇ ◆ ⎊) を画面から除去 ((a) or (b) いずれか) | §4.1 (b) SideRail 全体削除採用 |
| 2 | SideRail.test.tsx の関連 assertion 更新 | §4.4 (削除) |
| 3 | 関連 design doc (aether.jsx 等) の整合性確認 | §4.5 (comment 追記) |
| 4 | jest-axe で a11y violation が発生しないこと | §4.4 (5 画面巡回確認) |

### 4.7 実機検証 trigger (Iron Law 6)

PR #677 マージ前に Idios に実機検証依頼:

- Tauri 起動で 5 画面巡回し layout 回帰確認:
  - DropScreen: D&D zone / 直近録画 list / SelectedCard レイアウト
  - DetectingScreen: AllaganSigil 中央配置 / progress bar 幅
  - CompleteScreen: BrightnessTimeline 幅 / matches list / sourceBox
  - PreviewScreen: panes (×2 video) 横並び / FrameStrip 幅
  - ExportScreen: 出力先 input / list / progressBox
- ALLAGAN identity (AllaganCorner / AllaganFrame) が画面 identity を維持しているか感覚確認

## 5. Risk / 衝突対応

### 5.1 Lane 並行衝突 risk

| 衝突軸 | 詳細 | 対応 |
| --- | --- | --- |
| #633 PR ↔ Lane V Phase 1 #691 (metadataStore catch path) | metadataStore 自体は触らないが、画面の error/hint state 表示に間接影響 | #633 PR Pre-flight で #691 PR 並行確認、先着 merge → `git merge origin/develop-0.2.0` で取り込み + 再 lint |
| #633 PR ↔ Lane V Phase 2 #694 (unified ErrorState refactor) | #694 は 5 screen + 3 modal consumer 一括 refactor | roadmap で **Wave 1 main 3 lane merge 後** に #694 を sequencing 済。本 spec が衝突を増やさない |
| #645 PR ↔ Lane I-B Group B #644 (lib.rs brightness_samples 出力) | 両者 lib.rs を触る可能性 | **#645 PR は #644 merge 後**を推奨。`extract_brightness_window` 追加だけなので merge 後 rebase 容易 |
| #677 PR ↔ 全 lane | SideRail.tsx + App.tsx のみ | 衝突 risk 最小、PR 順序自由 |
| #633 PR ↔ Lane V Phase 1 #698 (DropScreen) | #633 issue body は DropScreen 触らない | 理論的衝突なし、Pre-flight 確認のみ |

**推奨 merge 順** (Lane II-a 内): #633 → #645 → #677

### 5.2 ffmpeg 関連 risk (#645)

| risk | 対応 |
| --- | --- |
| TaskStop で child process leak | `wait_with_output` で同期待ち、`run_in_background: true` を使わず `await invoke` 経路 (`feedback_taskstop_child_process_leak.md`) |
| ffmpeg 8.1 fps filter PTS offset 制約 (#575) | ±5s 表示用なので影響軽微。doc に「±~1.1s offset 可能性」明記 |
| GPU/CPU でデコード差異 | scope 外。CPU でも 100 frame ~200ms 想定 |

### 5.3 a11y risk (#633 / #677)

| risk | 対応 |
| --- | --- |
| SampleModeBanner: `aria-live="polite"` で読み上げ過多 | `polite` (assertive ではなく) で適切。banner mount 時 1 回のみ通知 |
| DisabledTooltip: `aria-describedby` 不採用方針 (a11y-policy.md) | 既存 pattern 維持 |
| jest-axe: SideRail 削除後 5 画面 violation なし | §4.4 |

### 5.4 doc drift risk (Group J #692 hint table check 連動)

`extract_brightness_window` 追加で `error.rs::default_hint_for_code` に 1 entry 追加 → `docs/tauri-commands.md` も同 entry 追加。Group J #692 (CI hint drift check) と整合確保。本 spec で文言 canonical を予約する。

## 6. 全受け入れ条件サマリ

| issue | priority | AC 数 | 充足 chapter |
| --- | --- | --- | --- |
| [#633](https://github.com/Idios/kobutachan-allaganeye/issues/633) | P2 | 10 | Chapter 1 (§2) |
| [#645](https://github.com/Idios/kobutachan-allaganeye/issues/645) | P3 | 6 | Chapter 2 (§3) |
| [#677](https://github.com/Idios/kobutachan-allaganeye/issues/677) | P3 (bug) | 4 | Chapter 3 (§4) |

doc 注記解消対象一覧:

- `docs/ui-interaction-spec.md` §1.2 / §1.4 アンチパターン例「派生 issue で対応予定」記述
- `docs/ui-interaction-spec.md` §2.3 / §2.4 / §2.5 の「§1.4 違反」「現状未実装」「§1.2 違反」注記
- `docs/ui-interaction-spec.md` §2.4 に MicroTimeline 状態機械追加
- `docs/tauri-commands.md` に `extract_brightness_window` 追加
- `docs/design/bundle/project/variants/aether.jsx` lines 438-453 inline rail comment 追記

## 7. 関連 doc / Iron Law 整合

### 関連 doc

- [`docs/l2-workflow.md`](../../l2-workflow.md) — PR Pre-flight / Self-Test Report / (A) PR 内修正優先 / 実機検証 trigger
- [`docs/ui-architecture.md`](../../ui-architecture.md) — 画面 5 + phase SM / 排他管理 / エラーハンドリング §4
- [`docs/ui-interaction-spec.md`](../../ui-interaction-spec.md) — UI 部品状態機械 (本 spec の主要 doc 編集対象)
- [`docs/a11y-policy.md`](../../a11y-policy.md) — `aria-describedby` 不採用 / focus visible / disabled 理由表示
- [`docs/tauri-commands.md`](../../tauri-commands.md) — `extract_brightness_window` 追加対象 (Group J #692 hint drift check 連動)
- [`docs/superpowers/plans/2026-05-11-l2-v020-roadmap-update.md`](../plans/2026-05-11-l2-v020-roadmap-update.md) — Lane II-a 親 plan

### Iron Law 整合 (`.claude/hooks/session-start.sh`)

- **Iron Law 1**: §6 で各 issue の AC を逐条マッピング、各 chapter §X.6 で対応箇所を表化
- **Iron Law 2**: 3 issue 順次対応 = 並列 bulk 操作なし、PR / commit は 3 PR 個別 (本 spec 内では bulk 操作未発生、必要時 AskUserQuestion)
- **Iron Law 3**: 1 PR = 1 chapter (= 1 issue) を厳守。spec 内に scope 範囲外の改善は含めない (例: BrightnessTimeline refactor は #694 に委譲)
- **Iron Law 4**: 各 PR は `Refs #N` のみ、`Closes` 禁止。マージ後 `/close-issue` で実測再検証
- **Iron Law 6**: 各 PR で `git fetch origin develop-0.2.0` + 並行 worktree PR 重複確認。実機検証 trigger は §2.7 / §3.8 / §4.7 で明示

### Memory feedback

- `feedback_taskstop_child_process_leak.md` — #645 ffmpeg subprocess の wait 必須
- `feedback_ffmpeg_test_interval.md` — #645 Rust integration test の 1 秒インターバル
- `feedback_skill_revision_empirical.md` — 大幅改訂時の empirical-prompt-tuning (本 spec scope 外)
- `feedback_gh_command_ja_heredoc.md` — PR 作成時の日本語本文は `printf | --body-file -` または HEREDOC

## 8. 着手前 Pre-flight チェックリスト (各 PR で再確認)

- [ ] `gh issue view <num>` で受け入れ条件をフルコピー (Iron Law 1)
- [ ] `git fetch origin develop-0.2.0 && git log HEAD..origin/develop-0.2.0 --oneline` で取り込み未済 commit 確認 (Iron Law 6)
- [ ] `gh pr list --search "<元 issue#>" --state all` で並行 worktree PR 重複確認 (Iron Law 6)
- [ ] #645 PR 着手時: Lane I-B Group B #644 の merge 状況確認 (lib.rs 共有)
- [ ] #633 PR 着手時: Lane V Phase 1 (#691 / #693 / #695 / #697 / #698) の並行 PR 状況確認
- [ ] 各 PR で path 別自動チェック実行 (`npm run lint` / `typecheck` / `test` / `build` / `cargo check`、Iron Law 6)
- [ ] 各 PR で実機検証 trigger 該当時に Idios に依頼 (`AskUserQuestion`、§2.7 / §3.8 / §4.7)
