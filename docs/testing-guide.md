# テスト実行ガイド

テストの実行方法、環境設定、およびトラブルシューティングのガイド。

テストの書き方（命名規則・fixture 配置等）は [`docs/coding-conventions.md`](coding-conventions.md) を参照。

## テスト実行コマンド

```bash
# 全テスト（slow マーカー除外）
pytest

# slow マーカー付きテストのみ（実動画が必要）
pytest -m slow

# slow を含む全テスト
pytest -m ""

# 特定のテストファイル
pytest tests/test_detector.py

# 特定のテスト関数
pytest tests/test_detector.py::test_function_name

# 詳細出力
pytest -v
```

### マーカー

| マーカー | 用途 | デフォルト |
| --- | --- | --- |
| `slow` | 実動画ファイルが必要なテスト全体（下記サブマーカーのスーパーセット） | 除外 |
| `slow_probe` | `probe_video()` のみ使用するテスト | 除外 |
| `slow_detect` | `detect_match_boundaries()` を実行するテスト | 除外 |
| `slow_pipeline` | `run_split()` 全パイプラインを実行するテスト | 除外 |
| `slow_gpu` | GPU アクセラレーション必須テスト | 除外 |
| `baseline_regen` | ベースライン再生成時のみ必要なテスト | 除外 |

`slow` および `baseline_regen` マーカーは `addopts = "-m 'not slow and not baseline_regen'"` で除外される。「slow はサブマーカーのスーパーセット」契約は `tests/conftest.py` の collection hook が機械的に強制しており、`slow_*` サブマーカーを単独付与すると、違反 item を collect する pytest 実行 (bare / `-m` 指定 / CI を含む) が `UsageError` (exit 4) で fail する (#812)。未登録マーカーの typo (例: `slow_detec`) は ini option `strict_markers = true` (pyproject.toml) が collection エラーで弾く (#812。addopts 内の `--strict-markers` は pytest 9.x で no-op のため不可)。

### マーカーの使い分け

```bash
# 高速サニティチェック（probe のみ、~30秒）
pytest -m slow_probe

# 検出テストのみ（~15-30分/録画）
pytest -m slow_detect

# 全パイプラインテスト（~20-40分/録画）
pytest -m slow_pipeline

# GPU テストのみ
pytest -m slow_gpu

# slow テスト全体（サブマーカー全含む。baseline_regen 付きテストも slow を
# 併せ持つため、現状は下の "slow or baseline_regen" と同一集合になる、#812）
pytest -m slow

# baseline_regen 含む全テスト（ベースライン再生成時の明示形）
pytest -m "slow or baseline_regen"
```

### 開発時の推奨テスト実行パターン

1. **コード変更後**: `pytest`（ユニットテストのみ、数秒）
2. **PR 作成前**: `pytest -m slow`（全 slow テスト。baseline_regen 付き class も含む、#812）
3. **検出アルゴリズム変更時**: `pytest -m "slow or baseline_regen"`（ベースライン検証含む）
4. **probe 周りの変更確認**: `pytest -m slow_probe`（高速確認）

## サンプル動画データの設定

実動画を使うテスト（`slow` マーカー付き）は、環境変数 `ALLAGANEYE_SAMPLE_VIDEO_DIR` で録画データのパスを指定する必要がある。

```bash
# Windows
set ALLAGANEYE_SAMPLE_VIDEO_DIR=E:\path\to\videos

# Linux / macOS
export ALLAGANEYE_SAMPLE_VIDEO_DIR=/path/to/videos
```

- 未設定の場合、`sample_video_dir` fixture を使うテストは自動的にスキップされる（テスト失敗にはならない）
- MKV: OBS の長時間録画（30-80GB、複数試合を含む）
- サブディレクトリ（`20260116/` 等）: 手動で試合分割済みの MP4（`YYYYMMDD_N.mp4`）

### 音声統合テスト primary 録画 (`ALLAGANEYE_AUDIO_TEST_VIDEO`)

`tests/test_audio_integration.py::test_primary_recording_fanfare_coverage` は、`audio/refs/fanfare.npz` を生成する際に使用した**そのままの**録画を必要とする。`ALLAGANEYE_SAMPLE_VIDEO_DIR` とは別管理。

- **指定変数**: `ALLAGANEYE_AUDIO_TEST_VIDEO`
- **対象ファイル**: `E:\videos\2026-04-08 21-14-05.mkv` (39 GB、full OBS 録画、8 fanfare starts を含む)
- **理由**: `fanfare.npz::metadata.source_filename` が指す特定ファイル。`ALLAGANEYE_SAMPLE_VIDEO_DIR` (`E:/royalstraightflesh/videos`) 配下ではないため、別 env で設定する

実行例:

```bash
ALLAGANEYE_AUDIO_TEST_VIDEO="E:/videos/2026-04-08 21-14-05.mkv" \
ALLAGANEYE_SAMPLE_VIDEO_DIR="E:/royalstraightflesh/videos" \
python -m pytest -m slow tests/test_audio_integration.py -v
```

primary 8/8 で ~30s。cumulative sample-dir tests (~90s) と合わせて音声統合の baseline をカバーする。

## GPU / ffmpeg テスト間インターバル

### 問題

ffmpeg を連続して呼び出すテスト（特に `--gpu` モード）で、NVIDIA ドライバが無応答になる現象が発生する。原因は GPU メモリの断片化で、短時間に多数の ffmpeg プロセスが GPU メモリの確保・解放を繰り返すことでドライバが不安定になる。

### 対策

`tests/conftest.py` に autouse fixture `_ffmpeg_interval` を実装し、`slow` マーカー付きテストの実行後に 1 秒のクールダウンを挿入する。

```python
@pytest.fixture(autouse=True)
def _ffmpeg_interval(request: pytest.FixtureRequest) -> None:
    yield
    if request.node.get_closest_marker("slow"):
        time.sleep(1)
```

- **対象**: `slow` マーカー付きテストのみ。通常のユニットテストにはインターバルを入れない（CI が不必要に遅くなるため）
- **タイミング**: テスト実行後（`yield` の後）にスリープする。テスト前にスリープすると最初のテストに不要な遅延が入る
- **1 秒の根拠**: GPU メモリの解放と再利用に十分な間隔。0.5 秒では不安定、2 秒以上はテスト全体の実行時間に影響が大きい

### 症状と診断

インターバルが不足している場合の典型的な症状:

- テストが途中でハング（タイムアウト待ち）
- `ffmpeg` プロセスが応答しなくなる
- Windows のイベントログに NVIDIA ドライバのリカバリ記録が残る

この症状が出た場合は、`_ffmpeg_interval` のスリープ時間を増やすか、テストを個別に実行して問題の再現性を確認する。

## baseline drift の判定

`tests/test_scorebar_regression.py::TestNoResolutionCompat` 系の baseline mismatch が発生した場合、(A) 検知ロジック退行 vs (B) ffmpeg version 依存差異 を以下の手順で判別する。

### 背景

`_scan_cpu` (および GPU chunked decode) の `fps` filter は ffmpeg version 依存でフレーム選択タイミングが変動し、極短 (< 1s) blackout を取りこぼすことがある (PR #575 で確定)。version upgrade のタイミングで他 baseline でも再発する可能性があるため、mismatch 発生時はまず差異の原因を判別する。

### 判定 flow

1. `allaganeye debug-brightness <video>` で per-frame `-ss` probe による実 brightness を CSV 出力
2. baseline 乖離が発生した timestamp 周辺で、極短 (< 1s) blackout (brightness < `blackout_threshold=15`) が存在するか確認
3. `_scan_cpu` の chunked fps filter 経路と比較する。`ffmpeg -vf "fps=N,showinfo" ...` で output PTS と実フレーム内容を `mean:[Y ...]` から確認できる
4. **per-frame probe で blackout を捕捉するが fps filter で捕捉しない場合** → (B) ffmpeg version 依存差異
   - `pytest -m "slow or baseline_regen"` で baseline を再生成し、現環境の正しい結果に固定する
   - 検知ロジック自体は安定しているため、他の baseline (`20260116` / `20260119` 等) は引き続き pass することを確認
5. **per-frame probe でも blackout を捕捉しない場合** → (A) 検知ロジック退行
   - 該当コミットを `git bisect` または review で特定
   - (B) と異なり baseline 更新で対処してはならない (退行を「正」と認めることになる)

### 事例

PR #575 / issue #560: ffmpeg 8.1 で `20260118` baseline の Match 8 end が 281s 乖離。per-frame probe で 6184.0-6184.8 の 0.8s 幅 blackout を捕捉できたが、`fps=0.5` filter は output PTS 6184 のラベルで実際は ~6185.1s 時点のフレーム (Y-mean=45) をサンプリングしていた (`showinfo` で確認)。(B) 案で baseline を `6184.0 -> 6465.25` に更新して対応。fps filter 廃止による根本対策は #576 で実施済み。

### detect fps filter 廃止後の運用 (#576)

PR #576 (detect fps filter 廃止) 完了後、default path では fps filter を
使わないため、ffmpeg version upgrade による Pass 1 brightness drift は
構造的に発生しない。本 S の判定 flow が必要になるのは、env var
`ALLAGANEYE_DETECT_FPS_FILTER=1` で legacy path を強制した場合のみ。

- 新 path で baseline mismatch が観測された場合は、(B) ffmpeg version
  依存 ではなく **(A) 検知ロジック退行** を疑う (legacy path で再現
  しないことを確認)
- legacy path は v0.3.x patch release で削除予定。それ以降は本 S の
  運用は廃止される

### 検証データの保存場所

PR #575 で取得した brightness 比較表 (per-frame probe vs chunked fps の対比) は [`docs/video-processing.md`](video-processing.md) §「ffmpeg fps filter の version 依存制約」に記録されている。

## v0.3.0 L3 work 用 regression baseline

v0.3.0 (= 新 L3) の Pillar 3 (perf 改善) と Phase 2b (scorebar ROI 適応) は既存 detect / export パイプラインを touch するため、改修前後で検知結果 + 書出し結果に regression がないことを **bit-exact baseline 比較** で保証する。

§baseline drift の判定 (ffmpeg version 依存差異) とは別軸で、**同一 ffmpeg version での実装変更 regression** を見る。

### baseline 動画セット (2 系統)

| 系統 | 動画 | 役割 |
| --- | --- | --- |
| OBS baseline | ALLAGANEYE_SAMPLE_VIDEO_DIR 配下の代表 OBS 録画 (Phase 1 child issue で N 本選定) | 正常検知可能な録画で改修後 regression なし保証 |
| VTuber primary benchmark | `E:\videos\gyawa_vatos\2772549129-...mp4` (7.5 GB, gyawa 提供 2026-05-18) | Phase 2 input adapt の primary test target + Pillar 3 robustness 検証 |

### baseline 定義

| 項目 | 内容 | 比較方法 |
| --- | --- | --- |
| 検知結果 | `metadata.json` の `matches` (`index` / `start_time` / `end_time` / `duration` / `type` / `output_file`) + `gaps` | bit-exact (JSON canonical 比較)。`detected_at` は除外 |
| 書出し結果 (split) | 試合 MP4 のファイルサイズ + SHA-256 hash | byte-exact (`-c copy` 無劣化のため決定論的) |
| 書出し結果 (export GUI) | encoder/version 依存で byte-exact 不可 | ffprobe メタデータ (長さ・解像度・fps・codec) + 任意 1 フレーム抽出 spot check |

### 配置規約

```text
tests/baselines/v0.3.0/
├── vtuber-primary-ground-truth.json     # VTuber 5 試合 ground truth (spec §8.6)
├── <obs-baseline-N>.metadata.json       # 改修前 detect 結果 snapshot
└── <obs-baseline-N>.split.json          # 改修前 split MP4 sizes + SHA-256
```

動画本体は repo に commit しない。metadata snapshot のみ commit。

### 比較スクリプト

```powershell
python scripts/compare-baseline.py tests/baselines/v0.3.0/<video>.metadata.json output/<video>/metadata.json
# exit 0 = match, exit 1 = diff detected
```

詳細仕様は [`docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md`](superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §8 を参照。

## プラットフォーム固有の注意点

### Windows

- ffmpeg のパス自動検索: `ALLAGANEYE_FFMPEG` 環境変数で BtbN LGPLv3 shared (配布物と同一、libdav1d 入り) を指定する運用を推奨 (#508)。既存 winget (`Gyan.FFmpeg`, GPL) のインストール先も後方互換で自動検索される
- GPU テスト: NVIDIA GPU + 最新ドライバが必要。GPU がない環境では自動的に CPU モードにフォールバックする

### Linux（未検証）

- GitHub Actions では `apt-get install ffmpeg` で lint/型チェック/ユニットテストを実行しているが、実動画での動作確認はしていない
- GPU テストは CI 環境では実行しない（GPU なし）

### macOS（未検証）

- Homebrew (`/opt/homebrew/bin`, `/usr/local/bin`) から ffmpeg を自動検索するコードはあるが動作確認なし
- CI 未構築
