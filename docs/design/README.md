# Allagan Eye — GUI Design Spec (A1 / Aetheric Observatory)

本ディレクトリは **Claude Design (claude.ai/design) からエクスポートされた GUI プロトタイプの handoff bundle** と、その実装に向けた仕様を保持する。L2a (#105) の設計の「単一ソース」となる。

## 画面フロー

```text
drop → detecting → complete → preview → export
```

- **drop**: 録画ファイルの受け取り (D&D / 参照 / 直近一覧)
- **detecting**: CLI 4 フェーズ (Detecting / Refining / Scorebar / Splitting) の進捗表示 + ライブログ
- **complete**: 検知結果レビュー (輝度タイムライン + 試合一覧 + 選択プレビュー)
- **preview**: **CLI 未サポートの新機能**。IN/OUT 2 画面プレビュー + 候補フレームストリップで境界微調整
- **export**: 編集結果を入力に ffmpeg で試合動画生成 (copy | h264)

## ターゲット技術 (確定: Tauri + React + TypeScript)

[#450](https://github.com/Idios/kobutachan-allaganeye/issues/450) は 2026-04-20 の Phase 0 実測結果をもとに **Tauri 2.x + React 19 + TypeScript** で確定。

動画プレイヤーの方針:

- MKV → fragmented MP4 への ingest 時 remux (`ffmpeg -c copy`)
- プレイヤーは axum HTTP サーバ (Rust 側、tower-http の `ServeFile` で 206 Partial Content 対応) 経由で動画配信
- フレーム精度シークは `requestVideoFrameCallback` + ffmpeg サムネイルキャッシュ
- CLI 呼び出しは `tokio::process::Command` + event emit で stdout ストリーミング

詳細な計測結果と採用根拠は [`feasibility.md`](feasibility.md) を参照。

handoff bundle の元推奨 (Electron) は Phase 0 で Tauri と比較計測した結果、Tauri が同等以上の性能と小さい配布サイズを実証したため非採用。[`bundle/project/Allagan Eye GUI.html`](bundle/project/Allagan%20Eye%20GUI.html) の「Claude Code 引き渡しガイド」の実装方針 (Electron 前提) は React 部分のみ参照する。

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

```text
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

**CLI 側の変更** (#463 で実装完了):

- `allaganeye detect <video>` — 検知のみ実行し metadata.json を出力
- `allaganeye split --from-metadata <metadata.json>` — 分割のみ実行
- `allaganeye split <video>` — 従来の一気通貫 (後方互換、内部で detect + split)

これにより CLI 単体でも従来通り使え、GUI は CLI の薄いラッパとなる。詳細スキーマと契約は [`../metadata-spec.md`](../metadata-spec.md) を参照。

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

### Phase 0: フィージビリティ検証 (済 2026-04-20)

Electron / Tauri の両方で最小プロトタイプを構築し F1-F5 を計測 → Tauri 採用確定。計測結果と採用根拠は [`feasibility.md`](feasibility.md) 参照。要点:

- MKV は両 FW とも `<video>` で直接再生不可 (Chromium ポリシー) → `ffmpeg -c copy` で fragmented MP4 に ingest 時 remux (38s / 2h 録画)
- フレーム精度: 両 FW p95 178-182 ms (目標 200ms 以内)
- 36 GB seek: Tauri http (axum) が p95 294 ms で Electron (352 ms) を上回る
- CLI streaming: 706s 長時間 detect で first-line 1.3-1.9s、両 FW streaming 成立
- Tauri 固有 blocker (tauri#6375, #5022) は現行 2.10.3 で再現せず

### Phase 1: データ層 (#463 完了)

- CLI を `detect` / `split --from-metadata` の 2 モードに分離 (後方互換維持)
- metadata.json スキーマを TypeScript 型 + zod schema に落とす
- Zustand による `useMetadataStore` (load / updateMatch / apply / clear)
- Rust Tauri commands (`load_metadata` / `apply_changes` atomic write + `metadata.original.json` backup)
- 契約詳細は [`../metadata-spec.md`](../metadata-spec.md) を参照

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

```text
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

## `gui/` — Tauri GUI 実装ディレクトリ (L2)

`#483` bootstrap で作成した Tauri 2 プロジェクト。`repo-root/gui/` に配置。

```text
gui/
├── package.json             — React + Vite + TypeScript + Zustand + @tauri-apps/*
├── vite.config.ts           — dev server 127.0.0.1:1420 固定
├── tsconfig.json / tsconfig.node.json
├── eslint.config.js         — ESLint 9 flat config
├── .prettierrc.json
├── index.html               — SPA エントリ (React マウントポイント)
├── src/                     — フロントエンド TypeScript
│   ├── main.tsx             — React root + F5/F12 等 production 時抑止
│   ├── App.tsx              — ルートコンポーネント (現在はプレースホルダ)
│   ├── styles/tokens.css    — aetherTheme デザイントークン (#464 で実装)
│   └── vite-env.d.ts
└── src-tauri/               — Rust バックエンド (Tauri 2 crate)
    ├── Cargo.toml           — tauri + dialog/fs/shell plugin + axum + tokio 他
    ├── tauri.conf.json      — CSP, window, bundle (active: false) 設定
    ├── capabilities/        — Tauri 2 permission モデル
    ├── icons/               — ico/png/Square*Logo (tauri icon で生成)
    └── src/
        ├── main.rs          — エントリ shim
        └── lib.rs           — tauri::Builder (axum 実装は #465 で追加)
```

**state 管理**: [Zustand](https://github.com/pmndrs/zustand) を採用 (#482 決定)。`useMetadataStore` 等は #463 Phase 1 で実装。

**実装知見**: [`phase0-tauri-reference.md`](phase0-tauri-reference.md) に Phase 0 (#468) で検証済みの全設定・コード片を保存。bootstrap はこのリファレンスを source of truth として展開した。

**開発者向けガイド**: [`../gui-development.md`](../gui-development.md) にセットアップ手順・CI 構成・トラブルシュート・バージョンポリシーを記載。

## 関連 issue

- [#105](https://github.com/Idios/kobutachan-allaganeye/issues/105) — GUI サポート (親)
- [#450](https://github.com/Idios/kobutachan-allaganeye/issues/450) — GUI フレームワーク決定 (Tauri + React + TS に確定 2026-04-20)
- [#451](https://github.com/Idios/kobutachan-allaganeye/issues/451) — プラットフォーム対応範囲
- [#452](https://github.com/Idios/kobutachan-allaganeye/issues/452) — インストーラ形式
- [#482](https://github.com/Idios/kobutachan-allaganeye/issues/482) — state 管理ライブラリ (Zustand 採用)
- [#483](https://github.com/Idios/kobutachan-allaganeye/issues/483) — Tauri プロジェクト bootstrap

## 反復

デザイン側で修正が必要になったら:

1. Claude Design 上で jsx を更新
2. 再 export → 本ディレクトリの `bundle/` を差し替え
3. 本 README と feasibility.md を同期

このディレクトリを「生きたスペック」として維持する。
