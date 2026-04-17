# システムアーキテクチャ

## 概要

Allagan Eye は FF14 フロントラインの長時間録画動画を段階的に処理するCLIツール。

## 段階的アーキテクチャ

```
┌─────────────────────────────────────────────────┐
│  L1: 試合分割                                     │
│  入力: OBS録画 (MP4/MKV)                          │
│  処理: ffmpeg 暗転検知 → FFmpeg 無劣化分割          │
│  出力: 試合ごとの MP4 + metadata.json              │
├─────────────────────────────────────────────────┤
│  L2: GUI（将来）                                   │
│  GUI サポート                                      │
├─────────────────────────────────────────────────┤
│  L3: メタデータ化（将来）                           │
│  入力: L1 出力の試合動画                           │
│  処理: OCR (キルログ) + 音声認識 (VC/SE)           │
│  出力: タイムスタンプ付きイベントデータ              │
├─────────────────────────────────────────────────┤
│  L4: 価値評価（将来）                              │
│  入力: L3 のイベントデータ                         │
│  処理: ローカル ML による投稿価値判定               │
│  出力: スコア + 推奨アクション                      │
├─────────────────────────────────────────────────┤
│  L5: 自動編集（将来）                              │
│  入力: L4 の判定結果 + L1 の動画                   │
│  処理: MoviePy/FFmpeg で切り出し + サムネイル生成   │
│  出力: 投稿用動画 + メタデータ + 投稿提案           │
├─────────────────────────────────────────────────┤
│  L6: guard 連携（拡張）                             │
│  allaganeye-guard 統合（--verify）                  │
├─────────────────────────────────────────────────┤
│  L7: 配布（拡張）                                  │
│  ゼロ環境構築配布                                  │
├─────────────────────────────────────────────────┤
│  L8: プライバシー・精密分割（拡張）                  │
│  プレイヤー名ぼかし、再エンコード分割モード          │
└─────────────────────────────────────────────────┘
```

> L6〜L8 は暫定計画。詳細は `docs/release-strategy.md` を参照。

## L1: 試合分割の設計

### UI変化検知

フロントラインの試合には以下の特徴的な画面遷移がある:

1. **ロード画面**: 暗転（黒画面）→ マップ表示
2. **試合中**: ゲームUI（HP/MPバー、ミニマップ、スコアボード）
3. **リザルト画面**: スコアボード、MVP表示
4. **退出後**: キャラクター画面 or 次の待機画面

### 検知戦略: 3段階パイプライン

試合境界の暗転には 3 パターンがあり、それぞれ異なる戦略で対応する:

| パターン | 特徴 | 対応戦略 |
|---|---|---|
| A: 長い暗転 | 7.0s 暗転 | Pass 1 の粗いスキャン + min_blackout_duration |
| B: 短い暗転 + ロビー | 2.5s 暗転 + ~51 brightness が 20s | transition expansion |
| C: 短い暗転 + 明るい画面 | 2.0s 暗転 + 即 brightness 79 | 2パス精密計測 |

**パイプライン**:

1. **Pass 1: 粗いスキャン** — 1-3s 間隔で全区間をプローブ。ffmpeg `-ss` 並列実行で暗転候補を収集
2. **transition expansion** — 暗転に隣接するロビー画面（brightness < 55）を暗転領域に含めて拡張（パターン B 対応）
3. **Pass 2: 精密計測** — 暗転候補を ±5s / 0.25s 間隔で再プローブし、正確な持続時間を計測（パターン C 対応）
4. **スコアバーフィルタリング** — `src_resolution` 指定時のみ。暗転前後のフレームを RGB プローブし、FL スコアバー（画面上部中央の 3GC 得点バー）の有無で暗転を分類。試合内暗転（キャラダウン等、< 3.5s）と非 FL 暗転を除外（#111）
5. **フィルタリング** — 持続時間で min_blackout_duration を判定し、リスポーン暗転を除外
6. **セグメント抽出** — 暗転領域間の非暗転区間を試合セグメントとして抽出（暗転内パディング付き）。隣接する暗転の分類から各セグメントに `type` を付与

**GPU モード** (`--gpu`): Pass 1 を GPU チャンク並列デコードで代替。動画を N チャンクに分割し、各チャンクで `-hwaccel auto` + `fps` フィルタの長寿命 ffmpeg プロセスを並列実行する。GPU 初期化コストを分散し高速化。Pass 2 以降は CPU/GPU 共通。利用不可時は CPU フォールバック。

### スコアバーフィルタリング (#111)

暗転検知だけでは分類できないパターン（キャラダウン暗転、非 FL コンテンツ暗転）を、FL スコアバーの有無で判別する。`detect_match_boundaries()` に `src_resolution` が渡された場合に有効化。

**スコアバー検出**: 暗転前後のフレームを RGB プローブし、画面上部中央（水平 35-65%、垂直 0-4%）の ROI を分析。ROI 内の RGB チャンネル間標準偏差が閾値を超える場合、FL スコアバー（3GC 色帯: 赤/青/黄）が存在すると判定。

**暗転分類**: 前後 3 フレーム（1 秒間隔）の多数決で 4 種に分類:

| 分類 | 条件 | 処理 |
|---|---|---|
| `in_match` | 前後ともスコアバーあり | < 3.5s → 除去、≥ 3.5s → 保持 |
| `match_boundary` | 片側のみスコアバーあり | 保持 |
| `non_fl` | 前後ともスコアバーなし | 除去 |
| `unknown` | プローブ失敗 | 保持（安全側） |

**セグメント type**: 隣接する暗転の分類からセグメントの種別を推論し、metadata.json に記録:

| 条件 | type |
|---|---|
| 両隣が `match_boundary` or `in_match` | `"fl_match"` |
| それ以外（先頭/末尾、unknown 隣接等） | `"unknown"` |

詳細は `docs/video-processing.md` を参照。

### 分割方式

- FFmpeg の `-c copy` で無劣化コピー（高速）
- キーフレーム境界で分割（暗転内パディングにより試合映像は切れない）

### 出力形式

```json
{
  "source": "2026-01-20 22-33-17.mkv",
  "source_duration": 7303.0,
  "source_duration_display": "2:01:43",
  "note": "Split times are approximate due to keyframe-aligned copy mode. ...",
  "matches": [
    {
      "index": 1,
      "start_time": 148.0,
      "end_time": 990.0,
      "start_display": "02:28",
      "end_display": "16:30",
      "duration": 842.0,
      "duration_display": "14m02s",
      "type": "fl_match",
      "output_file": "match_001.mp4"
    }
  ],
  "gaps": [
    {"start_display": "50:12", "end_display": "75:39", "duration_display": "25m27s"}
  ]
}
```

## 外部ツール依存

| ツール | 用途 | 必須 | 検索方法 |
|---|---|---|---|
| ffmpeg 4.1+ | 動画分割・暗転検知プローブ | Yes | PATH -> `ALLAGANEYE_FFMPEG` 環境変数 -> OS 別既知パス（自動検索） |
| ffprobe 4.1+ | 動画メタデータ取得 | Yes | 同上 |
| typer (Python) | CLI フレームワーク | Yes | pip |
| numpy (Python) | フレーム輝度計算 | Yes | pip |
| scipy (Python) | 音声特徴量の相互相関計算 | Yes | pip |
| opencv-python-headless (Python) | scorebar V2 検出（GC エンブレム判定, #307） | Yes | pip |

## クロスプラットフォーム対応

全モジュールが OS 非依存（subprocess + pathlib + numpy + scipy + opencv）。ffmpeg のパス検索のみ OS 別ロジックあり（`ffmpeg_path.py`）。

| 優先度 | OS | 状態 | ffmpeg 自動検索 |
|---|---|---|---|
| 1 | Windows | 対応済み | winget (`Gyan.FFmpeg`) |
| 2 | Linux | 未検証 | パッケージマネージャで PATH に入る（CI は lint/型チェックのみ） |
| 3 | macOS | 未検証 | Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`) |

## セキュリティ検査（allaganeye-guard）

外部ユーザーから受領した動画ファイルを処理する前に、独立ツール `kobutachan-allaganeye-guard` でセキュリティ検査を行う。

- **リポジトリ**: `Idios/kobutachan-allaganeye-guard`（独立パッケージ）
- **依存方向**: allaganeye → guard（一方向。guard は allaganeye に依存しない）
- **連携方式**: subprocess 呼び出し（`allaganeye-guard verify --json <file>`）
- **オプション依存**: `pip install allaganeye[guard]` で一緒にインストール可能。なくても動作する

詳細は `docs/guard-integration.md` を参照。

## ML モデル対応（将来: L4）

ローカル ML（scikit-learn 等）による投稿価値の評価を予定。具体的な技術選定は L4 着手時に再検討する。
