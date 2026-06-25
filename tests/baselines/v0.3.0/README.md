# v0.3.0 Regression Baseline Set

> **Status**: selection finalized (#778) / generation pending (#779)
> **Spec**: [docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md](../../../docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md) §8

## 目的

v0.3.0 L3 Pillar 3 (perf 改善) と Phase 2b (scorebar ROI 適応) のうち **detect / split (`-c copy`) 系統の regression 検出** 用に固定する改修前 snapshot。Phase 1 Wave 1a (#576 detect fps filter 廃止) のような検知ロジック改修 PR の Self-Test Report で「baseline diff 0」を `scripts/compare-baseline.py` で証明するために使用する。

検証 surface は spec §8.2 で定義される `matches` + `gaps` のみ (bit-exact)。`detected_at` 等の time-varying field は projection で除外される。

### Scope (本 baseline が covers すること)

- `allaganeye detect <video>` の `metadata.json` 出力 (matches + gaps) bit-exact
- `allaganeye split --from-metadata` の出力 MP4 (FFmpeg `-c copy` remux) の SHA-256 + size bit-exact

### Out of scope (本 baseline は covers しないこと)

| 領域 | 理由 | 別の検証ルート |
| --- | --- | --- |
| GUI H264 再エンコード (#591) | 入力 codec / GPU vendor / driver で出力 byte が変動 = 元々 deterministic regression に向かない | Python 側の `is_gpu_encoder_failure` / encoder fallback unit test (`tests/test_export_ffmpeg_runner.py`、#761 で encoder ロジックを Python subprocess 化) |
| 非 OBS 録画 (Game DVR / VTuber / Twitch) | Pillar 2 (input adapt) の scope。形式別に別 baseline を要する | `vtuber-primary-ground-truth.json` (VTuber 用 ±10s 比較、Pillar 2b で commit 済) |
| 非 AV1 codec 入力 (h.264 / hevc) | サンプルは OBS NVENC AV1 統一。codec パスごとの regression は別 baseline | 別途 codec multi-baseline (#576 完了後の Pillar 3 後続枠で再評価) |
| 非 NVIDIA GPU 環境 (AMD / Intel / CPU only) | 検知パスでは `--gpu` の vendor 選択は metadata.json `system_info.gpu_vendor_used` に記録されるのみ。出力 surface (`matches` / `gaps`) は同一の boundary 抽出結果になる想定 | 必要なら別 vendor 環境で同一動画を再検知して `compare-baseline.py` を re-run (env-specific verification は Self-Test Report の machine-unverifiable 行で扱う) |
| Portable ZIP size (#752) / GUI HTTP server (#670) | 検知出力に無関係 | 各 PR で個別検証 |

## 種類

| 種別 | ファイル | 内容 | 比較方法 |
| --- | --- | --- | --- |
| OBS baseline | `obs-<label>.metadata.json` | 改修前の `allaganeye detect` 出力 (snapshot) | bit-exact (Phase 1) |
| OBS baseline (split) | `obs-<label>.split.json` | 改修前の `allaganeye split --from-metadata` 出力の SHA-256 + size | bit-exact (Phase 1) |
| VTuber ground truth | `vtuber-primary-ground-truth.json` | user 手動検証済みの "正解" 試合 timestamp | ±10s 一致 (Phase 2b) |

OBS baseline は「現状検知の固定 snapshot」、VTuber ground truth は「目視正解」という別概念。OBS は **検知ロジック改修 PR で detect / split 出力が変わらないこと** を確認、VTuber は **scorebar ROI 適応化で正解に近づくこと** を確認する。本 OBS baseline は GUI H264 再エンコードや encoding fallback など別の regression を担保しない (§Out of scope 参照)。

## OBS baseline 動画セット (#778 選定)

### 選定基準

- **サイズ多様性**: 短尺 (~1h) / 中尺 (~2h) / 長尺 (~2.5h) を含み、detect 処理時間が perf 改修でどう変わるかを scale 別に観測できること
- **試合数 / gap 多様性**: matches 3 〜 9 + gaps 0 〜 2 を含み、splitter / metadata 書出し / gap detection の regression を異なる場面で確認できること
- **代表性**: 既に `tests/baselines/{20260116,20260118,20260119}.json` で scorebar V2 (#522 / #529) を validate 済みの 3 本を含み、過去の検出挙動との連続性を保つこと
- **再現性**: Idios 個人 OBS 録画 (`ALLAGANEYE_SAMPLE_VIDEO_DIR` 配下) で deterministic に再検知可能であること

全動画とも 1920x1080 / 60fps / AV1 codec (OBS NVENC AV1 録画) で、入力多様性は duration と match count に集約される。VTuber / Game DVR 等の異種入力は Phase 2 (Pillar 1) 着手時に別途追加検討。

### 選定リスト (5 本)

下表の Matches / Gaps は #779 で実測した改修前 snapshot 値 (`tests/baselines/v0.3.0/<label>.metadata.json` を参照)。

| Label | Source path (相対: `$ALLAGANEYE_SAMPLE_VIDEO_DIR`) | Duration | Size | Matches | Gaps | 採択理由 |
| --- | --- | --- | --- | --- | --- | --- |
| `obs-20260209` | `2026-02-09 23-12-24.mkv` | 57m06s (3426.5s) | 19.2 GiB | 3 | 0 | 最短 / fast smoke 用 |
| `obs-20260127` | `20260127/2026-01-27 21-59-15.mkv` | 1h01m11s (3671.3s) | 22.9 GiB | 3 | 2 | 短尺枠 2 本目 / gap 検出含む edge (#576 fps filter 改修時に gap 抽出も regression 確認) |
| `obs-20260116` | `20260116/2026-01-16 22-12-57.mkv` | 2h01m43s (7303.5s) | 37.0 GiB | 6 (うち 1 件 `unknown`) | 0 | scorebar V2 validated / 末尾 `unknown` 分類 edge |
| `obs-20260118` | `20260118/2026-01-18 22-15-18.mkv` | 2h17m14s (8234.7s) | 34.2 GiB | 5 | 2 | scorebar V2 validated / Limsa 待機暗転含む (#529) / 異常長尺 1 試合 (40m33s) edge |
| `obs-20260119` | `20260119/2026-01-19 22-09-07.mkv` | 2h33m54s (9234.0s) | 59.1 GiB | 9 | 1 | scorebar V2 validated / 高 match 数 |

合計 detect 時間 (実測): 34m43s (RTX-class GPU、`--gpu` モード、#779 PR generation log)。

### 不採用候補と理由

| 候補 | 理由 |
| --- | --- |
| `20260123/2026-01-23 22-27-10.mkv` (2h21m, 62.5GB) | 採択した `obs-20260118` / `obs-20260119` と duration / match 帯が重複し、追加情報量小 |
| `20260219/2026-02-18 21-55-03.mkv` (5h05m, 104.6GB) | 単独で detect 30 分超を要し、全 PR の Self-Test Report で常用するには重い。Phase 1 完了後の長尺枠強化フェーズで再評価 |
| Root 直下の長尺 MKV (`2026-01-20 22-33-17.mkv` 他、14 本) | scorebar V2 validation 履歴がなく、選定済み subdir 5 本で size × match の代表性は満たせている |
| Root の `2026-03-05 17-13-29.mkv` (5MB) | 試用試写 fragment と推定、FL match を含まない可能性高い |

## ファイル命名規約

- OBS baseline: `obs-<YYYYMMDD>.metadata.json` / `obs-<YYYYMMDD>.split.json`
  - `<YYYYMMDD>` は subdir 名 (`20260116` 等)、または root MKV の場合は録画開始日 (`20260209` 等)
- VTuber ground truth: `vtuber-<provider>-ground-truth.json` (例: `vtuber-primary-ground-truth.json`)

## Schema 参照

- `obs-<label>.metadata.json`: `allaganeye detect` の standard `metadata.json` 出力 ([`docs/cli-spec.md`](../../../docs/cli-spec.md) §metadata.json)。比較は spec §8.2 で定義された `matches` + `gaps` projection (`scripts/compare-baseline.py` が実装)
- `obs-<label>.split.json`: #779 で確定する schema (`splits[].output_file` / `size_bytes` / `sha256`)
- `vtuber-*-ground-truth.json`: spec §8.6 (`matches[].index` / `start_time` / `end_time` / `duration` / `type` / `tolerance_sec`)

## 関連

- spec: [§8 Regression prevention baseline](../../../docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md)
- 選定 issue: [#778](https://github.com/Idios/kobutachan-allaganeye/issues/778)
- 生成 issue: [#779](https://github.com/Idios/kobutachan-allaganeye/issues/779)
- 比較スクリプト: [`scripts/compare-baseline.py`](../../../scripts/compare-baseline.py) (#777)
- baseline drift (別軸 / ffmpeg version 依存): [`docs/testing-guide.md` §baseline drift の判定](../../../docs/testing-guide.md)
