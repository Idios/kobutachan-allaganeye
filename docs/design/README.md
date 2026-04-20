# Allagan Eye — GUI Design Spec (A1 / Aetheric Observatory)

本ディレクトリは **Claude Design (claude.ai/design) からエクスポートされた GUI プロトタイプの handoff bundle** と、その実装に向けた仕様を保持する。L2a (#105) の設計の「単一ソース」となる。

## 画面フロー

```
drop → detecting → complete → preview → export
```

- **drop**: 録画ファイルの受け取り (D&D / 参照 / 直近一覧)
- **detecting**: CLI 4 フェーズ (Detecting / Refining / Scorebar / Splitting) の進捗表示 + ライブログ
- **complete**: 検知結果レビュー (輝度タイムライン + 試合一覧 + 選択プレビュー)
- **preview**: **CLI 未サポートの新機能**。IN/OUT 2 画面プレビュー + 候補フレームストリップで境界微調整
- **export**: 編集結果を入力に ffmpeg で試合動画生成 (copy | h264)

## ターゲット技術 (未確定)

handoff bundle の推奨: **Electron + React + TypeScript**。ただし [#450 GUI フレームワーク決定](https://github.com/Idios/kobutachan-allaganeye/issues/450) でユーザー最終判断待ち。

判断材料は [`bundle/project/Allagan Eye GUI.html`](bundle/project/Allagan%20Eye%20GUI.html) 末尾の「Claude Code 引き渡しガイド」§1 (動画プレイヤーの実装方針) を参照。

## デザインシステム (色・タイポ)

`bundle/project/variants/aether.jsx` の `aetherTheme` が正。抜粋:

| トークン | 値 | 用途 |
|---|---|---|
| `bg` | `#0a0e14` | 基本背景 |
| `bgDeep` | `#05070b` | サイドバー等の深い背景 |
| `panel` | `linear-gradient(180deg, #0f1420 0%, #0a0e14 100%)` | パネル背景 |
| `gold` | `#c8a35c` | アクセント主色 |
| `goldBright` | `#e8c47a` | ハイライト |
| `goldDim` | `#8a7040` | 非アクティブ |
| `cyan` | `#4ac3d9` | 輝度線・強調 |
| `text` | `#d8cfbb` | 基本テキスト |
| `textDim` | `#8a8270` | 補助テキスト |
| `danger` | `#c87058` | エラー・警告 |

| フォント | 用途 |
|---|---|
| `Cinzel` (`"Trajan Pro"`, `"Cormorant Garamond"` fallback) | UI 見出し (ceremonial) |
| `Inter` (`"Segoe UI"` fallback) | 本文 |
| `JetBrains Mono` (`"Consolas"` fallback) | コード・数値 |

## データ契約

`bundle/project/shared/metadata.js` の `window.AE_META` を実装時 TypeScript 型へ変換する。

### CLI 分離 (重要)

```
CLI (dry-run)
  └→ metadata.json  ← 観測結果。CLI は書き換えない
      ├→ GUI がロード
      │  └→ GUI 編集 = 一時オブジェクト
      │     (start_time / end_time / name / type / split / skip)
      ├→ [適用] ボタンで overwrite
      │  └→ 元ファイルは metadata.original.json に退避
      └→ GUI が [書き出し] で ffmpeg を呼ぶ
          └→ 編集後 metadata を入力として match_xxx.mp4 を生成
```

**CLI 側の変更**: 現行の `allaganeye split` を 2 コマンドに分離:
- `allaganeye detect <video>` — 検知のみ実行し metadata.json を出力 (現 `--dry-run` 相当)
- `allaganeye split --from-metadata <metadata.json>` — 分割のみ実行

これにより CLI 単体でも従来通り使え、GUI は CLI の薄いラッパとなる。

### GUI 側拡張フィールド

```typescript
interface Match {
  // 既存
  index: number;
  start_time: number; end_time: number;
  start_display: string; end_display: string;
  duration: number; duration_display: string;
  type: 'fl_match' | 'unknown';
  output_file: string;

  // GUI 追加
  name?: string;        // GUI で付けた表示名
  type_override?: 'fl_match' | 'unknown' | 'skip';
  edited?: { start_time: number; end_time: number };
}
```

## 実装 Phase

実装は #105 (GUI 親 issue) で Phase 0-4 の子 issue を起票して進める。

### Phase 0: フィージビリティ検証 (framework 確定後)
- MKV を `<video>` タグ (Electron) / 採用 framework のメディア API で再生可能か
- 60 fps 録画で 1 フレーム単位シークが実用速度 (目標 200ms 以内) か
- 2 時間超のファイルで seek が破綻しないか
- NG 時の代替: low-res proxy (480p h264) 事前生成

結果は [`feasibility.md`](feasibility.md) に記録。

### Phase 1: データ層
- CLI を `detect` / `split --from-metadata` の 2 モードに分離
- metadata.json スキーマを TypeScript 型へ落とす
- 読み込み / 編集 / 保存の state 管理 (Electron 採用なら zustand か Redux)

### Phase 2: 画面骨格 (5 画面 + ルータ)
- `bundle/project/variants/aether.jsx` のコンポーネント形状を TS に写経
- 色・フォントを `aetherTheme` をそのまま CSS 変数化

### Phase 3: preview 画面の本物化
- `<video>` タグ + ffmpeg サムネキャッシュ (`~/.allaganeye/cache/<hash>/thumbs/*.webp`)
- キーボードショートカット (←→ 1s / shift 10s / ⌥ 1F / space 再生)
- 編集の一時状態管理

### Phase 4: export の本物化
- ffmpeg 呼び出し (copy / h264)
- 進捗取得 (ffmpeg stderr パース)
- 試合別進捗 + 完了後フォルダを開く

## 画面ごとの仕様

各画面の詳細は handoff HTML の該当 jsx を参照。主要ポイント:

### 1. drop
- D&D + 参照ボタン + 直近録画リスト
- 録画ドロップで `detecting` へ

### 2. detecting
- 4 フェーズバー (Detecting / Refining / Scorebar / Splitting)
- リアルタイムログ (CLI stdout を行単位で流す)
- 中断ボタン
- 中央のアラガン紋章が回転 (観測中の視覚フィードバック)

### 3. complete
- 輝度タイムライン + 黒フェードバンド + 試合ブロック
- 試合行クリックで選択、ダブルクリックで `preview` へ
- 「全試合書き出し」で `export` へ直行

### 4. preview (新機能)
- **IN / OUT 2 画面** `<video>` タグ
- 候補フレームストリップ (±3s, 12 frames @ 0.5s 間隔)
- 微細タイムライン (±5s, 輝度 + 閾値)
- ステッパー (−10s / −1s / −1F / +1F / +1s / +10s)
- TC 数値入力 (HH:MM:SS.ff)
- キーボード: ←→ 1s / shift ←→ 10s / ⌥ ←→ 1F / space 再生
- 試合名 / type 編集可

### 5. export
- 出力先 / 命名規則 / コーデック選択 (copy | h264)
- 試合別進捗 + 完了後フォルダを開く

## 非機能要件

- 2:50:28 の録画で全操作 60 fps
- preview での 1 フレームシーク目標 200 ms 以内

## スクリーンショット

`screens/` ディレクトリは空 (本 handoff 時点では未収録)。Idios が手動で 5 枚 (drop / detecting / complete / preview / export) のスクリーンショットを取得して追加予定。Claude はブラウザ描画・スクショ取得を行わない (handoff bundle README の指示による)。

## ファイル構成

```
docs/design/
├── README.md              — 本ファイル (設計仕様・実装 Phase のインデックス)
├── feasibility.md         — Phase 0 フィージビリティ検証の記録場所 (Phase 0 完了時に埋める)
├── screens/               — 各画面スクショ (後日 Idios が追加)
└── bundle/                — handoff bundle 原本 (変更不可、参照のみ)
    ├── README.md          — handoff 発行元 (Claude Design) からの CODING AGENTS 向け指示
    └── project/
        ├── Allagan Eye GUI.html      — エントリ HTML (全画面カタログ)
        ├── design-canvas.jsx         — デザインキャンバス (参考)
        ├── shared/
        │   ├── common.jsx            — 共通ヘルパ (fmtTime, StateSwitcher, WindowChrome 等)
        │   └── metadata.js           — metadata.json サンプルデータ + 輝度波形
        └── variants/
            ├── aether.jsx            — A1 メイン (drop/detecting/complete)
            ├── aether-preview.jsx    — A1 preview 画面 (境界調整 UI)
            ├── neon.jsx              — B variant (参考、採用しない)
            └── ops.jsx               — C variant (参考、採用しない)
```

## 関連 issue

- [#105](https://github.com/Idios/kobutachan-allaganeye/issues/105) — GUI サポート (親)
- [#450](https://github.com/Idios/kobutachan-allaganeye/issues/450) — GUI フレームワーク決定 (Electron + React + TS が handoff 推奨)
- [#451](https://github.com/Idios/kobutachan-allaganeye/issues/451) — プラットフォーム対応範囲
- [#452](https://github.com/Idios/kobutachan-allaganeye/issues/452) — インストーラ形式

## 反復

デザイン側で修正が必要になったら:
1. Claude Design 上で jsx を更新
2. 再 export → 本ディレクトリの `bundle/` を差し替え
3. 本 README と feasibility.md を同期

このディレクトリを「生きたスペック」として維持する。
