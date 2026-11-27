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

### KO / ASSIST の GT 突合ハーネス (`tests/test_indicators_gt.py`)

`allaganeye indicators` の検出精度を **recall / precision** で評価する (`slow` マーカー)。
GT は `tests/fixtures/indicators_gt/*.json` に人間が裁定した表示の一覧として置いてある。

```bash
# 全ケース (2 本は全区間 0.1 秒走査、他 HUD 1 本は窓のみ) = 約 8 分
ALLAGANEYE_SAMPLE_VIDEO_DIR=... ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER=... pytest -m slow tests/test_indicators_gt.py
# 実測値 (recall / precision / missed / extra) を表示する
pytest -m slow tests/test_indicators_gt.py -s
```

- 評価は**切り抜き単位**（区間の開始が ±0.5 秒以内）。近接表示の分割 / 併合は問わない
- しきい値は KO / ASSIST 別に recall >= 0.8 / precision >= 0.8（元 issue の初期案）
- 全区間走査は CI では実行しない（サンプル動画が無い）。**検出ロジックを変えた PR では
  ローカルでこのハーネスを回し、数値を PR 本文に載せる**
- 実測値の正は [`docs/superpowers/specs/2026-11-12-l4-ko-assist-indicator-appearance.md`](superpowers/specs/2026-11-12-l4-ko-assist-indicator-appearance.md) §7.9

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

### VTuber 検証用 VOD (`ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER`)

L3 の VTuber/masked 系 slow テスト（`tests/test_l3_phase2_parity.py` / `tests/test_vtuber_region_e2e.py` / `tests/test_vtuber_ground_truth.py` / `tests/test_vtuber_gt_regression.py` / `tests/test_areamap_slow.py` の masked ケース）は、`ALLAGANEYE_SAMPLE_VIDEO_DIR` とは別の VOD 置き場を `ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER` で参照する（未設定時の既定: `E:/allaganeye-samples`）。

- 配置: 配信者別の FF14 FL VOD（mp4）。未配置・未設定の場合、該当テストは skip される
- 空文字で設定した場合も未設定と同様に既定 path へフォールバックする（`os.environ.get(...) or` 規約で統一）
- `tests/test_vtuber_gt_regression.py` は release gate **G3** ([`docs/release-process.md`](release-process.md) §レイヤーリリース受け入れゲート) の実体 (#895 P3 / PR #915)。6 source GT のうち gyawa のみ別 root を使い、`ALLAGANEYE_SAMPLE_VIDEO_DIR_GYAWA`（既定 `E:/videos/gyawa_vatos`）で解決する (#915 F18 で絶対 path 直書きを廃止)
- `ALLAGANEYE_VTUBER_GT_REQUIRE_ALL=1` を設定すると、VOD 不在による skip を fail に格上げできる。「6 source gate が silent に 5 source へ縮退」する事故の検出用 (#915 F18)

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

## サンプル動画/GT データの保全 ([#869](https://github.com/Idios/kobutachan-allaganeye/issues/869))

前 § までの実動画データは再入手不能な録画を含み、E: 単一コピーの喪失 = 実動画 baseline gate / GT 突合の恒久不能化となる (bus factor 1)。2026-07-07 に以下の保全方針を決定した。

### 方針 (対象・先・周期)

| 項目 | 決定 |
| --- | --- |
| 対象 | **検証依存セット (48 ファイル、~632 GiB)** = GT/baseline 台帳が参照する全動画 (下表)。台帳外の自録画・再生成可能な検知/分割出力・重複 zip は対象外 |
| 先 (第 2 系統) | `F:\allaganeye-backup\` (E: とは別物理ディスクの内蔵 HDD) へ robocopy cold copy |
| 先 (第 3 系統) | 筐体外の系統を 1 つ追加する。方式 (外付け HDD / クラウド cold storage / 併用) の選定・購入・初回コピーは Idios 判断 |
| 周期 | 定期実行ではなく**新規 baseline/GT 動画の追加時に都度コピー + 台帳更新**。release gate 時に checksum 照合で健全性を確認 |
| 台帳 | [`tests/baselines/source-videos.sha256.json`](../tests/baselines/source-videos.sha256.json) に全対象の SHA-256 + size を記録 (repo = GitHub 側にも残る)。ドライブ故障後の復元・再入手時の同一性検証に使う |

#### 実施状況

上表は **2026-07-07 に決めた方針**であって現状ではない。現状は次のとおり:

| 系統 | 状態 |
| --- | --- |
| 第 2 系統 (`F:`) | **完了** (#869) |
| 第 3 系統 (筐体外) | **未着手**。[#882](https://github.com/Idios/kobutachan-allaganeye/issues/882) で追跡中 |

`F:` は `E:` と**同一筐体内の内蔵 HDD** なので、ディスク単体故障には耐えるが **PC 全損・ランサム・盗難に対しては現状 2 系統とも無防備**である。第 3 系統はその穴を塞ぐためのもので、未着手である以上その穴は今も開いている。

#### 台帳と原本の照合記録

**台帳 = 実在保証ではない。** これまでに実行した突合の結果を、実施時期つきで残しておく。

| 系統 | 照合の実施時期 | 結果 |
| --- | --- | --- |
| E: 原本 | 2026-08-21 | 48 entry 中 **8 本が欠落** (すべて `obs-baseline-manual-split` の手動分割 MP4)。うち 1 本は [#992](https://github.com/Idios/kobutachan-allaganeye/issues/992) で復元済みのため、記録時点の欠落は **7 本**。扱いは [#998](https://github.com/Idios/kobutachan-allaganeye/issues/998) で追跡中 |
| F: バックアップ (第 2 系統) | [#869](https://github.com/Idios/kobutachan-allaganeye/issues/869) の初回コピー時 (方針決定は 2026-07-07)。**以降は再照合していない** | 全件照合で **fail=0/48**。#992 の復元は実際にここを復元元として使えた |

欠落している 7 本は**どのテスト / GT manifest からも参照されていない** (参照元は台帳自身と `docs/superpowers/` 配下の記録のみ) ため、現時点でテストが赤くなることはない。台帳から落とすか E: へ復元するかの判断は #998 で行う。

> 上表は**突合を実行した時点の記録**であり、この doc を読んだ時点の状態ではない。現在の状態が要るときは台帳を使って実際に突合すること。

### 検証依存セット (対象一覧)

| category | 場所 | 内容 | 参照する検証 |
| --- | --- | --- | --- |
| `obs-baseline-source` / `obs-baseline-manual-split` | `$ALLAGANEYE_SAMPLE_VIDEO_DIR` (`2026-02-09 23-12-24.mkv` + subdir `20260116` / `20260118` / `20260119` / `20260127` 丸ごと) | v0.3.0 baseline 5 本の source MKV + 手動分割 MP4 | bit-exact baseline gate (§v0.3.0 L3 work 用 regression baseline、#778/#779) |
| `masked-obs-source` | `$ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER/20250527-29/20250527-29/` | masked 検証用 OBS MKV 3 本 | masked GT 検証 (L3 Phase 2) |
| `vtuber-vod` / `vtuber-mask` | `$ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER` 直下 | 配信者 VOD 5 本 (mp4) + mask PNG 3 枚。**Twitch archive 消滅後は再入手不能** | L3 位置独立検証 (multi-source) |
| `vtuber-primary` | `$ALLAGANEYE_SAMPLE_VIDEO_DIR_GYAWA`（既定 `E:\videos\gyawa_vatos\`） | primary GT の source VOD (gyawa 提供 2026-05-18、7.5 GB) | `vtuber-primary-ground-truth.json` (±10s 突合) / VTuber timeline GT gate G3 の gyawa source (#915) |
| `game-dvr-4k` | `E:\videos\M1wa_zeromus\` 直下 | 4K Game DVR source 5 本 (mp4)。`split_*/` 配下は allaganeye 出力 = 再生成可能なため対象外 | scorebar V2 Rescue path (#522) の HUD スケール差異検証 |
| `audio-primary` | `E:\videos\2026-04-08 21-14-05.mkv` | `fanfare.npz` source (§音声統合テスト primary 録画) | 音声統合 baseline (`ALLAGANEYE_AUDIO_TEST_VIDEO`) |

対象外 (バックアップ不要):

- `$ALLAGANEYE_SAMPLE_VIDEO_DIR_VTUBER/20250527-29.zip` (270 GB): 展開済み MKV と重複
- `_masked_a_out/` / `_p2_vtuber_out/` / `M1wa_zeromus/split_*/` 等の検知・分割出力: source から再生成可能
- 台帳外の OBS 録画 (`E:\royalstraightflesh\videos` の残り MKV / `E:\videos` の 2026-04 以降録画、~1.3 TB): 検証台帳が参照しないため本方針の対象外。保全価値は録画者判断

### コピー手順 (Idios 手動実行)

バックアップ先は `F:\allaganeye-backup\<root-key>\<相対 path>` のミラー構造とする。root-key は台帳 `roots` のキー (`royalstraightflesh-videos` / `allaganeye-samples` / `videos`) と一致させる。

```powershell
$B = 'F:\allaganeye-backup'
# OBS baseline (root MKV 1 本 + subdir 4 個)
robocopy 'E:\royalstraightflesh\videos' "$B\royalstraightflesh-videos" '2026-02-09 23-12-24.mkv' /DCOPY:DAT /R:2 /W:5
foreach ($d in '20260116','20260118','20260119','20260127') {
    robocopy "E:\royalstraightflesh\videos\$d" "$B\royalstraightflesh-videos\$d" /E /DCOPY:DAT /R:2 /W:5
}
# masked OBS MKV 3 本
robocopy 'E:\allaganeye-samples\20250527-29\20250527-29' "$B\allaganeye-samples\20250527-29\20250527-29" /E /DCOPY:DAT /R:2 /W:5
# VTuber VOD + mask PNG (直下のみ、zip と出力 dir は含めない)
robocopy 'E:\allaganeye-samples' "$B\allaganeye-samples" *.mp4 *.png /DCOPY:DAT /R:2 /W:5
# E:\videos 配下 (gyawa primary / 4K Game DVR source / audio primary)
robocopy 'E:\videos\gyawa_vatos' "$B\videos\gyawa_vatos" /E /DCOPY:DAT /R:2 /W:5
# M1wa は直下の source mp4 のみ (split_* 出力 dir は対象外のため /E を付けない)
robocopy 'E:\videos\M1wa_zeromus' "$B\videos\M1wa_zeromus" *.mp4 /DCOPY:DAT /R:2 /W:5
robocopy 'E:\videos' "$B\videos" '2026-04-08 21-14-05.mkv' /DCOPY:DAT /R:2 /W:5
```

### checksum 照合手順 (コピー後・復元時・release gate)

台帳と突合する。バックアップ側は `$backupBase` 配下の root-key ミラー構造で、E: 側原本は台帳 `roots` の原本 path で解決する (`$backupBase = $null` に切り替える)。

```powershell
# -Encoding UTF8 必須: PS 5.1 は BOM なし UTF-8 を cp932 として読むため、
# 省略すると日本語/絵文字ファイル名の entry (vtuber-vod 等) が化けて MISSING 誤報になる
$m = Get-Content 'tests\baselines\source-videos.sha256.json' -Raw -Encoding UTF8 | ConvertFrom-Json
$backupBase = 'F:\allaganeye-backup'   # E: 側原本を照合する場合は $null にする
$fail = 0
foreach ($e in $m.entries) {
    if ($backupBase) { $rootPath = Join-Path $backupBase $e.root }
    else { $rootPath = $m.roots.($e.root).path }
    $p = Join-Path $rootPath $e.path
    if (-not (Test-Path -LiteralPath $p)) { $fail++; Write-Output "MISSING  $p"; continue }
    $h = (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower()
    if ($h -ne $e.sha256) { $fail++; Write-Output "MISMATCH $p" }
}
Write-Output "verify done: fail=$fail / total=$($m.entries.Count)"
```

`fail=0` で健全。全 48 ファイル (~632 GiB) の照合は HDD 読み出しで 1-2 時間かかるため、release gate では対象 category を絞った spot check (例: `obs-baseline-source` のみ) でもよい。

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

## KO / ASSIST 走査の実測 (#1140)

`allaganeye indicators` の走査は **チャンク並列 + ffmpeg 側 crop** になっている。
速度の正は本節の実測値で、しきい値 (ワーカー上限 / 最小チャンク長) の SSoT は
`allaganeye/video/indicator_scan.py` の docstring。

### 測定条件 (2026-11-18)

- 動画: `20260116_1.mp4` (944.1 秒 / 9441 フレーム @ 0.1 秒)
- バンド: `(x=550, y=623, w=252, h=54)` (fps 1.0 レイアウト、1080p)
- 機械: 32 論理コア / Windows / venv の Python 3.12

### before / after

| 経路 | 実測 | 倍率 |
| --- | --- | --- |
| before: 逐次 1 ffmpeg + フルフレーム (1920x1080) | 227.9 秒 | 1.0x |
| after: 8 ワーカー + ffmpeg crop (252x54) | 59.1 秒 | 3.9x |

> その後の #1147 (スケール探索を ±5% 3 段へ) で **28.0 秒** になっている。
> 比較と根拠は後節「スケール探索の絞り込み (#1147)」を参照。

**検出結果は完全一致** (9441 フレームの `(時刻, 種類, スコア)` が同一、
イベント 30 件 / 30 件)。crop 導入後も一致するのは、切り出し座標を
`band_crop_rect` 1 か所から取っているため (`tests/test_indicators.py` が pin)。

### ワーカー数のスケーリング (300 秒スライス)

| ワーカー | 時間 | 秒あたりフレーム |
| --- | --- | --- |
| 1 | 70.6 秒 | 42.5 fps |
| 2 | 37.4 秒 | 80.3 fps |
| 4 | 21.4 秒 | 139.9 fps |
| 8 | 17.3 秒 | 173.7 fps |

デコードのみ (照合なし) は 300 秒で 9.2 秒。**照合がボトルネック**で、
8 ワーカーでも 4.1x に留まるのは GIL 競合 (cProfile では `filter2D` が総時間の
89%、1 フレームあたり 14 回の NCC = 7 スケール × 2 テンプレート)。

### スケール探索の絞り込み (#1147)

走査のスケール倍率は ±5% の 3 段 (`0.95 / 1.00 / 1.05`) を既定にしている
(SSoT は `allaganeye/video/indicators.py` の `_SCAN_SCALE_FACTORS`)。
±20% の 7 段 (`_DEFAULT_SCALE_FACTORS`) は `match_text` の診断用に残している。

#### GT 3 本での比較 (2026-11-18、GT ハーネスと同じ校正・同しきい値)

| 動画 | layout scale | 7 段 | ±5% (3 段) | 1 点 (1.00) |
| --- | --- | --- | --- | --- |
| `20260116_1.mp4` (944 秒) | 1.0 | 57.5 秒 / recall 0.968 / precision 1.0 | **28.0 秒** / recall 0.968 / イベント 30/30 一致 | 14.8 秒 / 同左 |
| `20260116_5.mp4` (880 秒) | 1.0 | 54.1 秒 / recall 1.0 | **27.8 秒** / イベント 51/51 一致 | 14.3 秒 / 同左 |
| `other_hud` (2 時間 43 分・GT 窓のみ) | **0.8** | 19.7 秒 / recall 1.0 | **9.8 秒** / イベント 5/5 一致 | 4.7 秒 / **recall 0.2 (4 件取り逃し)** |

**1 点に絞ると他 HUD で取り逃す** (アンカー由来の scale 0.8 は実際の表示より
約 5% ずれていた)。±5% なら 3 本とも全件一致する。

#### 実際に勝った倍率 (合格候補の内訳)

| 動画 | 1.00 | 1.05 | それ以外 (0.90 / 0.95 / 1.10 / 1.15 / 1.20) |
| --- | --- | --- | --- |
| `20260116_1.mp4` | 439 | 0 | 0 |
| `20260116_5.mp4` | 643 | 0 | 0 |
| `other_hud` | 0 | 67 | 0 |

±10% 以上は 3 本で一度も使われていない。±5% は観測値を含みつつ、未見の HUD に
対する余白を 1 段残す。

#### 2.8 時間換算

944 秒を 28.0 秒で走査 = 約 34 倍速。2.8 時間 (10,080 秒) は **約 5 分**
(並列化前の逐次 1 段は 227.9 秒 = 4.1 倍速で、約 41 分だった)。

既知の弱点: キャリブレーション誤差が ±5% を超える録画では取り逃しうる。
その場合は `--region` で手動指定するか、GT を追加して `_SCAN_SCALE_FACTORS` を
再検討する (`tests/test_indicators.py` の
`test_scan_scale_factors_reject_far_off_scales` が現在の許容幅を pin している)。

### 明度プリフィルタ (#1149)

`match_text` は倍率ごとに「バンド全体の明るい画素が `0.45 x 最小 core` 未満なら
**その倍率の NCC をすべて飛ばす**」プリフィルタを持つ。テンプレートごとの
`bright_fraction >= 0.45` は窓の中の割合を見ているので、バンド全体で足りなければ
どの位置でも合格しえない (**判定を変えない**ことが保証される)。しきい値は
**実際に照合するテンプレート**から毎回導出する (カスタムテンプレートでも同じ保証を保つ。
SSoT は `allaganeye/video/indicators.py` の `_prefilter_threshold_for()`)。

#### 実測 (2026-11-18、`20260116_1.mp4`、8 ワーカー + ±5% 3 段)

| 項目 | 値 |
| --- | --- |
| スキップ率 (全編 9441 フレーム) | **23.4%** (2208 フレーム、しきい値 349.2 px) |
| スキップ率 (先頭 300 秒だけ) | 47.4% (試合開始前の暗い区間が多いため。全体とは違う) |
| 走査時間 | 28.0 秒 -> **25.0 秒** (37.7 倍速) |
| イベント数 | 30 件 (変化なし) |

#### デコードが次の上限

同じ 944 秒のデコードのみ (crop あり、8 ワーカー) は 300 秒スライスで 4.7 秒。
944 秒に換算すると約 **14.8 秒**で、25.0 秒のうち過半を占める。つまり
照合をこれ以上削っても **残りは 10 秒程度**しかない。更に速くするには
ハードウェアデコード (NVDEC / QSV / D3D11VA) が必要で、`gpu_detector.py` に
同じパターンがある (crop と併用するときは `-hwaccel_output_format` +
`hwdownload` が要る。 #899 参照)。

#### 2.8 時間換算

37.7 倍速なので 10,080 秒は **約 4.5 分** (並列化前は約 41 分)。

### ハードウェアデコード (`--gpu`、#1151)

`indicators --gpu` は `detect --gpu` と同じ vendor 選択 (`gpu_detector` の表) で
デコードをハードウェア化する。crop / fps フィルタは CPU 側なので、surface を
GPU に持つ vendor (D3D11VA / QSV) は filter 先頭に `hwdownload,format=nv12,` を
挿入する。失敗時は CPU で 1 回だけ自動再実行する。

#### 実測 (2026-11-18、`20260116_1.mp4`、NVIDIA + AMD 機)

1 ストリーム 300 秒のデコードのみ (crop あり):

| 経路 | 時間 | フレーム checksum |
| --- | --- | --- |
| CPU | 9.44 秒 | 3173898855 |
| `-hwaccel cuda` (auto-download) | 6.95 秒 | 同し |
| `-hwaccel cuda -c:v h264_cuvid` | 6.58 秒 | 同し |
| `-hwaccel d3d11va -c:v h264` + hwdownload | 6.23 秒 | 同し |

**出力画素は完全一致**。ただし 8 並列にすると差は小さくなる:

| 8 並列で 944 秒をデコード | 時間 |
| --- | --- |
| CPU | 12.9 秒 |
| cuda (cuvid) | 12.0 秒 |
| d3d11va | 11.3 秒 |

end-to-end (crop + ±5% 3 段 + 明度プリフィルタ + 8 ワーカー):

| 経路 | 時間 | イベント |
| --- | --- | --- |
| CPU | 25.3 秒 | 30 件 |
| `--gpu` | **24.2 秒** | 30 件 (完全一致) |

**利得が小さい理由**: 8 並列のソフトウェアデコードは既にホスト I/O で飽和しており、
デコードは並列でも 2.3 倍しか伸びない。したがってこの構成では `--gpu` は数 %。
**4K 録画 / コア数の少ない環境 / 照合と CPU を奪い合う状況**では相対的に効く見込み
(未検証)。パイプ読み出しの粒度 (1 フレーム vs 64 フレーム) は無関係だった。

## GUI mutation testing (#1154)

GUI (`gui/`) のテスト品質とデッドコード整理のため、[mizchi/mutator](https://github.com/mizchi/mutator)
（diff 駆動の mutation testing）を導入している。**初回は全ソース、以後は差分だけ**を回す。

### 前提

- `gui` の `vitest` は **5.1.1**（mutator の Vitest アダプタが `vitest ^5.0.0` を要求するため。#1154 以前は 4.1.12）
- mutator 本体は **Node.js 24 以上**（`gui/package.json` の `engines` ではなく依存側の要求）。
  CI の `gui-frontend` job は node 22 のままで `npm test` は動く（vitest 5 の engines は `^22.12 || ^24 || >=26`）が、
  **mutation testing を CI に載せる場合はその job だけ node 24 にする**（今は未常設）
- 設定は `gui/mutator.config.ts`、入口は `gui/scripts/mutation.mjs`（`npm run test:mutation`）

### コマンド

```bash
cd gui
npm run test:mutation                            # 初回 full / 2 回目以降は差分のみ (自動)
npm run test:mutation:status                     # 前回の full run が今のソースに有効か (FRESH / STALE)
npm run test:mutation -- --plan                  # 実行せず「どのモードで何を測るか」だけ見る
npm run test:mutation -- --reporter simplify    # デッドコード候補を出す（台帳は更新しない）
npm run test:mutation -- --reporter agent > .mutator/agent.json  # agent 用 JSON（wrapper のログは stderr なので stdout は JSON だけ）
npm run test:mutation -- --kill-matrix          # 検出力ゼロ / 包含されるテストを出す
npm run test:mutation -- --include 'src/utils/*.ts'   # 部分実行 (全ソース扱いにしない)
MUTATION_FULL=1 npm run test:mutation            # 差分モードでも全ソースを再実行
MUTATION_SINCE=origin/main npm run test:mutation # 差分の基準を変える（狭すぎる基準は自動で退けられる）
npx mutator accept <key> --reason "<理由>"       # equivalent mutant を理由付きで除外
```

### 「全ソースを 1 回測ったら、ソースが変わるまでやらない」の管理

2 つの成果物で管理する。

| file | 場所 | 役割 |
| --- | --- | --- |
| `.mutator/full-run.json` | ローカルのみ（gitignore） | この端末の cache が全ソース分揃っているかの印。**差分の基準**（`--since`）を決める |
| **`gui/mutation-baseline.json`** | **コミットする** | 計測結果の台帳。**CI はこれだけを見る** |

**日常の手順（GUI のソース / 設定を変えたとき）**:

1. **変更を commit してから** `cd gui && npm run test:mutation` — 差分だけ計測する（2 回目以降は数秒〜数分。judgment は関数単位でキャッシュ）
2. 完走すると **`gui/mutation-baseline.json` が自動で書き換わる** → そのまま commit する
3. `npm run test:mutation:status` で `FRESH` を確認する
4. CI の `mutation-baseline` job が同じ判定を行う（**STALE なら red**）

**計測は commit 後に行う**。台帳は「ある commit の内容を測った」という CI への証明なので、
計測対象（`src/**` / config / 入力 file）に未コミットの変更があると wrapper は**台帳を書かない**
（dirty な状態で測った内容はどの commit にも存在せず、差分の基準にもできない。dirty で計測 →
その変更を revert → 別 hunk を編集、の順で未計測の範囲が差分外に残る。codex review 2026-11-19 P1）。
台帳自身は計測対象外なので、「計測 → 台帳を commit」の順で未コミットのまま `FRESH` になる。

```text
$ npm run test:mutation:status
[mutation] 計測済みの範囲: 2026-11-26T12:14:58.394Z mode=full (status 0 / 全ソース 8601 mutants (1816 survived))
[mutation] 判定: STALE — 1 ファイルが変わった
  M src/utils/time.ts
[mutation] 次にやること: cd gui && npm run test:mutation
  (差分だけ計測し、計測結果を gui/mutation-baseline.json に書き戻します。commit してください)
```

台帳（`schemaVersion: 2`）の中身:

| フィールド | 内容 |
| --- | --- |
| `completedAt` / `mode` / `status` | 計測日時 / `full` か `incremental` か / mutator の終了コード |
| `sources` | `src/**/*.{ts,tsx}`（**テスト含む**）の件数と内容ハッシュ |
| `config` | **計測対象 / 結果を決める** file（`mutator.config.ts` / `vite.config.ts` / `package{,-lock}.json` / `tsconfig.json` / `../schemas/metadata.schema.json`）の内容ハッシュ |
| `head` | 計測時点の commit。次の差分の基準（`--since`）に使い、その値の妥当性を git で検証する |
| `entries` | 追跡対象 1 file ごとの path + sha256。**src 配下の全 file**（`.ts` / `.tsx` に加えてテストが読む CSS / JSON 等）と config / 入力 file を含む |
| `fullRun` | 直近の**全ソース**計測の集計（差分 run でもこの値は引き継ぐ） |
| `carriedFrom` | 差分 run のとき、どの計測から引き継いだか |

- **テストファイルもハッシュ対象**。テストを変えると killer が変わるので、
  「ソース不変なら再計測不要」の判定にテスト変更を含めないと嘘になる
- テストが直接読む file（`src/styles/tokens.css` 等）も `entries` に含める。
  これがないと、CSS を変えただけで `FRESH` を返してしまう（codex review 2026-11-19 P2）
- 改行コードは LF に正規化してからハッシュする（Windows の CRLF checkout と CI の LF で
  同じ値になるように。これがないと CI が常に STALE になる）
- `config` ハッシュが変わったら `--since` を付けず**自動で full に戻す**（include scope /
  ランナー / 依存 / テスト入力が変わると、未計測 / 再計測が必要な mutant が生じるため）
- **設定は 2 種類に分ける**。`config`（上の 6 file）は full を強制、
  `mutator.accepted.json` と `scripts/mutation.mjs` は `entries` にだけ入れて
  **full を強制しない**（accept は通常運用で、計測結果自体を変えないため）。
  変更は `STALE` として検出され、次の差分 run で台帳に記録される
- `schemaVersion` が想定外 / `head` がない・不正なら **STALE**（未知 / 旧形式の台帳を FRESH と
  誤認しない。`head` が無いと次の差分の基準を検証できないので、CI と wrapper で契約を揃える）
- 差分 run でも台帳は更新する（「前回の台帳 + 今回の差分 = 全ソース計測済み」が成り立つ）。
  一方 `.mutator/full-run.json` は**全ソース run のときだけ**書く
- 台帳の集計（`fullRun`）は**直近の全ソース run の値**。差分 run で上書きしない
  （snapshot はその run のスコープしか持たないため）
- **完走の証拠を検証する**: 全ソース run のあと snapshot に `Pending` が残っていたら
  （config の `timeBudget` / `mutantsPerLine` 等で打ち切られた）台帳を書かない。汚染された
  config は marker / 台帳に記録されないので、以後も full のまま止まる（codex review 2026-11-19 P1）
- **計測中の変更を検出する**: 台帳に書く直前にハッシュを取り直し、run 開始時と違えば台帳を書かない
  （長い full run の間にソースを編集すると、別の内容を測った結果で前の内容を certified にしうる）
- ハッシュは **バイナリ安全**（テキスト拡張子だけ CRLF→LF 正規化、それ以外は byte のまま）。
  symlink は**リンク文字列**をハッシュする（リンク先の内容を読むと git から見て無変更なのに
  ハッシュが変わる）。gitignore された file は「計測対象に未追跡 file がある」として台帳を書かない

### CI ゲート

`.github/workflows/ci.yml` の `mutation-baseline` job が
`node gui/scripts/mutation.mjs --status` を実行する（node の標準モジュールだけで動くので
`npm ci` 不要・数秒）。**STALE / 台帳なしなら fail**。
計測自体は CI で回さない（1 時間規模なので）。開発者が手元で完走させて台帳を commit するのが正規経路。

### 実行モードの切り替え（marker と argv）

| 状態 | 実行内容 |
| --- | --- |
| ローカル marker なし / **marker が壊れている・旧形式** | 全ソース（`--since` を付けない）。完走で marker と台帳を書く（marker は**存在だけでなく中身を検証**する。壊れた marker を掴むと未計測のまま差分モードに入るため） |
| marker あり・差分の基準が変更を網羅 | **2 pass**: ① `--since <前回計測時点の commit> --fail-on-survived`（変更ソースのゲート）② `--since … --include-test-changes`（テスト変更分も計測して台帳更新） |
| marker の `config` ハッシュが不一致 | 全ソース（設定 / 依存 / テスト入力の変更で再計測が必要になるため） |
| `--since` の基準が前回計測以降の変更を網羅しない | 全ソース。`MUTATION_SINCE` の上書き値が使えない場合は**前回計測時点の commit** に戻して再判定する |
| `--include` / `--exclude` / `--only` / `--since` を明示 | そのまま渡す（marker も台帳も触らない） |
| `--reporter` を明示（差分モード） | 1 pass（`--since --include-test-changes`）。**台帳は更新しない**（ゲートを挟まないため） |
| `--time-budget` / `--mutants-per-line` / `--shard` を明示 | 全ソース（`--since` を付けない）。**marker も台帳も書かない**（`Pending` が残るため） |
| `--config-file` / `--root` / `--runner` / `--config` / `--jest-config` / `--playwright-config` を明示 | そのまま渡す（実効スコープを argv から確定できないので **台帳も書かない**） |
| `--exclude-mutator` / `--plugin` / `--scope` / `--experimental-callgraph` / `--full-dry-run` / `--shared-cache` / `--no-arid` / `--arid-callee` / `--no-weak-mutation` / `--[no-]typecheck` / `--critical` / `--threshold-break` を明示 | 同上（計測対象 / 判定が変わるので台帳を書かない） |
| `--no-fail-on-survived` を明示 | **無視**する。差分モードのゲートは外せない（fail-closed） |
| `--status` | 計測せず FRESH / STALE だけを返す |
| `--plan` | 計測せず、選んだモード / `since` / 実際に渡す argv を表示する |
| `--help` / `-h` / `--version` / `-v` | 何もしない |
| `MUTATION_FULL=1` / `--full` | marker があっても全ソース（marker と台帳を更新） |

**台帳を書く条件は「スコープ制限なし、`--reporter` なし（差分モード時）、終了コード 0 / 2、
`--time-budget` 等なし、差分範囲の妥当性検証を通る」のすべて**。
`--time-budget` 付きの full run は mutant を `Pending` のまま残すので「全ソースを測った」
証拠にならない（書いてしまうと次の run が差分モードに入り、未計測のファイルが永久に測られない。
codex adversarial-review 2026-11-19 P1）。**未完走のまま kill すると cache が保存されない**
（Ctrl+C / タイムアウト kill で 48 分を 2 回捨てた実例あり）。区切るなら `--time-budget`
を使い、最後に 1 回完走させて台帳を書かせる。

**差分の基準は「前回の計測時点の commit」**（台帳 / marker の `head`）を使う。release base（`origin/develop-x.y.z`）
を基準にすると、base が前進（develop の取り込み）したときに「base 側の変更が差分に入らない」ため
full run が避けられない。前回計測の commit を基準にすれば、「前回の計測 + 今回の差分 = 全ソース計測済み」
が常に成り立つ（差分の基準は `npm run test:mutation -- --plan` で見られる）。

**基準の妥当性検証**は 3 段。どれかが崩れたら full run に落とす（codex review 2026-11-19 P1）。
mutator は `git diff <since>` ではなく **`git diff <merge-base(since, HEAD)>`** で mutant を選ぶので、
検証もそれに合わせる。

1. **履歴**: 前回計測の commit が今の HEAD の履歴にあるか。別ブランチ / 別 worktree の台帳を
   持ってきた場合、その commit は HEAD の祖先でなく、差分は fork 点から計算されるため
   「計測していない部分」が差分外に残る
2. **merge-base**: `merge-base(base, HEAD)` が前回計測の commit 以前か。それより新しいと、
   計測時点から merge-base までの変更が差分に入らない
3. **作業ツリー**: 前回計測から内容が変わった**計測対象**（`src/**/*.{ts,tsx}`）が全部
   その差分（未追跡 file を含む）にあるか

`MUTATION_SINCE` で明示指定した値が検証を通らない場合は、前回計測時点の commit に戻して再判定する
（いきなり 40 分超の full run に落ちないように）。

> **削除だけの差分は 0 件になる**: mutator の `--since` は「新しい側の行」に立つ mutant を選ぶ。
> デッドコード削除だけの PR では 1 pass 目（ゲート）が `0 in the diff` になり、ゲートは実質空振りする
> （検証自体は 2 pass 目と `--status` で成立する）。2026-11-27 の PR #1155 がこの形だった。

snapshot の有無ではなく marker で判定するのは、**`--include` 付きの部分実行でも
`.mutator/snapshot.json` が書かれる**ため（部分実行で差分モードに入ると、未計測の
ファイルが永久に測られなくなる）。`.mutator/` は gitignore だが
**`mutator.accepted.json` だけはコミットする**（equivalent mutant の理由をレビュー可能にするため。
`gui/.gitignore` は `.mutator/*` + `!.mutator/mutator.accepted.json`）。

> **注意（実測 2026-11-26）**: `snapshot.json` は**実行スコープ単位で置き換わる**。
> `--include` 付きの部分実行をすると、その時点の full run のキャッシュが消え、
> 次の full run が全 mutant を再実行する（8,601 mutants で約 48 分）。
> 部分実行は **full run を済ませた後**に行い、頻繁に切り替えない。

### 実測（2026-11-26、Windows / 32 論理コア、`--concurrency 32`）

**全ソース完走（marker 記録済み）**:

| 項目 | 値 |
| --- | --- |
| 対象 | 134 files（`src/**/*.{ts,tsx}` のうち mutation 対象） |
| mutant 総数 | **8,601** |
| 内訳 | Killed 2,954 / Survived 1,813 / NoCoverage 462 / CompileError 3,170 / Timeout 189 / RuntimeError 5 / Ignored 8 |
| mutation score | **58.0%** |
| 所要 | 47 分 33 秒（うち typecheck 約 10 分。typecheck はキャッシュされない） |

**改善前後の比較（`src/utils/brightness.ts`、帯ごとの境界値を pin するテストを追加）**:

| 時点 | killed / executed | score |
| --- | --- | --- |
| 追加前 | 68 / 85 | 55.8%（ファイル単位） |
| 追加後 | 80 / 85 | **96.5%** |

残る 3 件は equivalent（空配列 2 件 + `d < 1.2` の `<=`。1.2 は二進小数で表現できないため
両者は同一に分類される）として `mutator.accepted.json` に記録した。

**既知の傾向**: 画面 (screens) が全 undetected の約 6 割を占める（MinimapScreen 533 /
ExportScreen 223 / DetectingScreen 191 / PreviewScreen 179 …）。これは「画面の分岐を
テストが変化させていない」ことの現れで、デッドコードではなく**テストギャップ**。
`--reporter simplify` の候補 817 件（224 関数）も同じ性質（`condition always true/false` が 661 件）。

**初回は 1 回で終わらない前提で回す**: GUI テストは jsdom + RTL で 1 mutant あたりが重く、
full run は **1 時間規模**（2026-11-26 実測 47 分 + typecheck）。`--time-budget` で区切りながら
回し、最後に 1 回完走させて台帳を書かせる。新規 clone では cache が無いので最初の 1 回だけ full になる
（台帳は commit 済みでも cache は `.mutator/` にしかない）。

### 生存 mutant の扱い

スコアは KPI にしない（equivalent mutant で 100% にはならない）。1 件ずつ次のいずれかで決着させる
（skill `mutation-test-loop` がこのループを回す）。

1. テストを足して殺す（`not detected` / `not infected` / `not reached` の分類ごとに、足すべき入力が違う）
2. コードを消す（`--reporter simplify` の削除系候補）
3. `npx mutator accept <key> --reason "<理由>"` で `mutator.accepted.json` に記録する（コミットする）

### 変更したときのチェックリスト（テスト状況を完了させる）

`gui/src/**` または `gui/mutator.config.ts` 等を変えた PR は、以下を満たしてから出す。

- [ ] `cd gui && npm run test:mutation` を**完走**させた（`--time-budget` で切ったままにしない）
- [ ] **計測対象を commit してから**計測した（未コミットのままでは台帳が書かれない）
- [ ] **変更したソース**に検出されない mutant が残っていない
      （`--fail-on-survived` が効く。残っていると台帳が更新されない）
- [ ] 新しく Survived / NoCoverage になった mutant を triage した
      （テスト追加 / デッドコード削除 / `accept` + 理由。未 triage のまま放置しない）
- [ ] `accept` した / `mutator.accepted.json` を変えた場合は、その後もう一度計測した
      （追跡対象なので台帳が `STALE` になる。accept 自体は計測を変えないので差分 run で足りる）
- [ ] 更新された `gui/mutation-baseline.json` を commit した
- [ ] `npm run test:mutation:status` が `FRESH`（CI の `mutation-baseline` job と同じ判定）

**ゲートの範囲**: `--fail-on-survived` は **変更したソース**（`--since <base>`）にだけ掛ける。
`--include-test-changes` の範囲（変更テストがカバーする関数 = 本 repo では 125 件の既存 survivor）
までゲートすると、無関係なテスト編集でも大量の triage を強いるため。テスト変更分は
2 pass 目で計測して台帳に反映する（ゲートはしない）。

**`--reporter` を明示した場合**は 1 pass（`--since --include-test-changes`）だけ回す。
`--reporter agent` は stdout に JSON を 1 つだけ出す前提なので、2 pass にすると JSON が
2 つ並んで壊れるため。この経路はゲートなし（gaps の確認用）なので **台帳は更新しない**
（更新してしまうと `--reporter` を付けるだけでゲートを迂回できてしまう。codex review 2026-11-19 P1）。
台帳を更新するときは `--reporter` を外して `npm run test:mutation` を実行する。
wrapper 自身のメッセージは **stderr** に出る（stdout は機械可読な出力に譲る）。

モード判定は `npm run test:mutation -- --plan` で実行前に確認できる（`mode` / `certify` /
`since` / 実際に渡す argv を表示）。「なぜ full になったのか」はこの出力と stderr の 1 行目で分かる。

Iron Law 6 の GUI チェック（AGENTS.md）にも含めてある。CI が red のときは
job のログに「どのファイルが変わったか」と次のコマンドが出る。

### エージェント skill

`@mizchi/mutator` 同梱の skill を `.agents/skills/` に配置している
（`npx mutator init-skill --dir .agents/skills` の出力。**ただし `mutator/SKILL.md` の
1 文だけ `--dir` 前提に直している** — upstream は Claude Code の既定 skill ディレクトリを
指しており、この repo の配置 (`.agents/skills/`) と合わないため。更新時は `--force` で上書きした後、
同じ 1 文を直す）。

| skill | 用途 |
| --- | --- |
| `mutator` | セットアップ / 実行 / レポートの読み方 / CI / 閾値 / accepted mutant（`references/` に詳細） |
| `mutation-test-loop` | 生存 mutant を 1 件ずつ潰すループ（`--reporter agent` → テスト追加 → `--only` で再確認 → accept） |

#### この repo で skill を使うときの前提

skill 本文は upstream のまま（`--dir` の 1 文だけ修正）なので、以下の読み替えが要る。

| skill の記述 | この repo では |
| --- | --- |
| 「project root で `npx mutator ...`」 | **`cd gui` で実行する**（mutation の対象は `gui/`。`mutator.config.ts` と `mutator.accepted.json` も `gui/` 直下） |
| `--since <base>` の base は「usually `main`」 | wrapper は**前回計測時点の commit** を自動で入れる（`MUTATION_SINCE` で上書き可、検証あり）。手で回すときは `--since origin/develop-x.y.z` でもよいが、直前の計測を無駄にしないなら wrapper 経由が良い |
| `--since <base>`（step 1） | **テストを変えたときは `--include-test-changes` を付ける**（wrapper は 2 pass 目で自動的に付ける）。付けないとテスト変更だけの差分が 0 件になり、追加したテストが検証されない（2026-11-26 実測: 0 件 vs 1,028 件） |
| `--fail-on-survived` | wrapper の 1 pass 目（変更ソース）で付与する。skill の step 1 には無いので、skill だけで回すときは `--fail-on-survived` を足す |
| `references/ci.md` の GitHub Action | **不採用**。計測は 1 時間規模なので CI では回さず、**台帳のハッシュ比較だけ**をゲートにする |
| `pnpm add -D` | `npm` で導入済み（`gui/package.json` に exact pin） |
| Node.js 24+ | 同上。CI の `gui-frontend` は node 22 のままで、mutation は回さない |

**skill の `npx mutator` を直叩きすると台帳（`gui/mutation-baseline.json`）は更新されない**
（wrapper の完走時だけ書く）。skill のループで作業した後は、最後に
`cd gui && npm run test:mutation` を 1 回完走させて台帳を更新する。
`--only` / `--include` は部分実行なので台帳を書かない（未完了のまま green にできない設計）。

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

### detect fps filter 廃止後の運用 (#576 → #864)

PR #576 (detect fps filter 廃止) で default path から fps filter が消え、さらに
PR #864 で legacy path と transitional な rollback env var ごと撤去された。
現在 detect の chunk decode は frame-index ベースの
`select='not(mod(n,N))'` のみで、**ffmpeg version upgrade による Pass 1
brightness drift は構造的に発生しない**。

- baseline mismatch が観測された場合、(B) ffmpeg version 依存差異 という
  選択肢は既に存在しない。**(A) 検知ロジック退行**として扱う
- 切り替えて再現確認するための legacy path はもう無いので、本 S 冒頭の
  (A)/(B) 判定 flow は #864 以降 **(A) 一択**に縮退している。以下の記述は
  v0.3.0 以前の baseline を追跡する際の歴史的経緯として残す

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
