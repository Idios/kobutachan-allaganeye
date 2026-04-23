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
|---|---|---|
| `slow` | 実動画ファイルが必要なテスト全体（下記サブマーカーのスーパーセット） | 除外 |
| `slow_probe` | `probe_video()` のみ使用するテスト | 除外 |
| `slow_detect` | `detect_match_boundaries()` を実行するテスト | 除外 |
| `slow_pipeline` | `run_split()` 全パイプラインを実行するテスト | 除外 |
| `slow_gpu` | GPU アクセラレーション必須テスト | 除外 |
| `baseline_regen` | ベースライン再生成時のみ必要なテスト | 除外 |

`slow` および `baseline_regen` マーカーは `addopts = "-m 'not slow and not baseline_regen'"` で除外される。

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

# slow テスト全体（サブマーカー全含む、baseline_regen 除外）
pytest -m slow

# baseline_regen 含む全テスト（ベースライン再生成時）
pytest -m "slow or baseline_regen"
```

### 開発時の推奨テスト実行パターン

1. **コード変更後**: `pytest`（ユニットテストのみ、数秒）
2. **PR 作成前**: `pytest -m slow`（全 slow テスト）
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
