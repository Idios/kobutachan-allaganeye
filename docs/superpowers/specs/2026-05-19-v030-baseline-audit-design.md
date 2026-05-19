# v0.3.0 OBS baseline ground-truth audit design (2026-05-19)

> **Status**: design (brainstorming 完了、writing-plans 入り口)
> **作成**: 2026-05-19 / session `hopeful-germain-8ffc43`
> **対象 issue**: [#796](https://github.com/Idios/kobutachan-allaganeye/issues/796)
> **目的**: PR #793 (#576 fps filter retirement) journey で偶発発見された baseline 精度問題 (F1-F4) を起点に、v0.3.0 の 5 OBS baseline 全件について **手動 visual verification による ground truth を確立** し、現 baseline (PR #793 後の `tests/baselines/v0.3.0/<recording>.metadata.json`) との diff から silent miss / false positive を体系的に洗い出す。本 audit 自体は #576 の merge / scope reduce / defer / abandon を **決めない** (= reexamination spec の入力を揃えるところまで)。

## 1. 背景

### 1.1 きっかけ

PR #793 (#576 detect fps filter retirement) 実装中、複数の baseline 精度問題が偶発的に発見された:

| # | Recording | Timestamp | 内容 | 発見契機 |
|---|---|---|---|---|
| F1 | obs-20260116 | t=3227.4 (3.6s blackout) | Match 3 end 56:07→53:50、legacy fps filter で silent miss、dual seek path で初検出 | Codex の spec reading |
| F2 | obs-20260116 | t=2175.7-2177.3 (~1.6s blackout) | sub-sample-interval boundary、Idios 視覚確認済の実試合境界、pre-A5 dual seek で deterministic miss、A5 で救済 | Idios の視覚確認 |
| F3 | obs-20260118 | t=2610.75 | sub-sample-interval boundary、pre-A5 dual seek で miss、A5 で救済 (legacy fps filter は非決定検出) | Pre-A5 baseline regenerate (commit 789a9b7) 中の偶発検出 |
| F4 | obs-20260118 | 3 件 1.4-2.1s 短時間 blackout | legacy fps filter drift で miss、新 v2 path で初検出 | dual seek + A5 実装後の差分 |

### 1.2 本質的問題

F1-F4 は PR #793 で fix 済とされているが、**発見が偶発的** であった点が本質的問題:

- systematic な ground-truth audit が未実施
- 他 baseline (obs-20260119 / 20260127 / 20260209) や既 audit 済 baseline (obs-20260116 / 20260118) の他箇所に、**未発見の silent miss / false positive が存在する可能性**を排除できない
- ベースライン精度が信頼できない状態では:
  - #576 の trade-off (perf -68% vs accuracy zero regression) を ground truth 基準で評価できない
  - A (ship PR #793) / B (A5 revert + dual seek ship) / C (#576 defer) のどれを選んでも、「真の正解状態に対して何 % 正しいか」が定量化できない
  - 将来の detect 改善 PR でも accuracy 退行を確実に検出できない

### 1.3 解決したい問題

1. **Ground truth の不在**: 5 OBS baseline の "正解" 試合境界が文書化されていない (現 baseline = 検知結果 snapshot に過ぎず、ground truth と区別されていない)
2. **偶発 → systematic への昇格**: F1-F4 の発見は spec reading や Idios の視覚確認による偶発的なもの。同等品質を 5 baseline 全件に展開する仕組みが必要
3. **Iron Law 6 Pre-flight の盲点**: PR 提出時の自動チェック (CI / acceptance criteria) は ground truth に対しては評価していない。本 audit がその穴を埋める

## 2. 採用方針 (brainstorming で決定)

| 論点 | 選択肢 | 採用 | 根拠 |
|---|---|---|---|
| **Claude 支援レベル** | (A) Minimum (diff script のみ) (B) Pre-screen 付き視聴 (C) Auto-suggest + Confirm | **(B) Pre-screen 付き視聴** | Idios workload 5-7.5h → 2-4h に短縮 (C) は ground truth の neutrality を損なう懸念あり (Claude の auto-extract が誤った場合に発見困難) |
| **Audit batching** | (X) Per-recording 逐次 (Y) 5 本一括 batch (Z) 増分 (1+4) | **(Z) 増分 (1 本 proof of concept → 残り 4 本 batch)** | obs-20260116 で end-to-end 実証 → script / worksheet の不足を spec に feedback → 残り 4 本 batch。やり直し cost が最小 |
| **Ground truth file format** | (a) `.txt` (issue 本文表記) (b) `.json` (vtuber-primary-ground-truth.json 既存 schema) | **(b) `.json`** | 既存 vtuber-primary-ground-truth.json と schema 統一 / diff 抽出 script が書きやすい / 既存 baseline metadata.json と同 family |
| **Spec doc 配置** | (i) 本 spec を docs/superpowers/specs/ (ii) docs/ 直下 | **(i) docs/superpowers/specs/** | 他 design doc と同 location / brainstorming → writing-plans の標準 path |
| **Finding 集約 doc** | (α) issue 本文の `docs/v030-baseline-audit.md` (β) 本 spec に統合 | **(α) `docs/v030-baseline-audit.md` 別 doc** | issue 本文と整合 / design (本 spec) と deliverable (audit doc) を分離 |
| **reexamination spec の扱い** | (P) 本 brainstorming で同時作成 (Q) audit 完了後に別 brainstorming | **(Q) 別 brainstorming** | reexamination spec は audit 結果 (findings list) が input。audit 完了まで実質書けない |

## 3. Workflow (3 stage)

### 3.1 Stage 1: Pre-screen (Claude)

**入力**:

- `tests/baselines/v0.3.0/<recording>.metadata.json` (現 baseline、PR #793 head)
- 元動画ファイル (`$ALLAGANEYE_SAMPLE_VIDEO_DIR/<recording-path>`)

**処理** (`scripts/audit-prepare.py`):

1. `<recording>.metadata.json` から matches[] と gaps[] の境界 timestamp を抽出
2. 各境界 (start_time / end_time) について、前後 ±5s の brightness 値を `allaganeye debug-brightness` 同等ロジックで CSV 出力
3. 各境界の 1s 前 / 0s / 1s 後の 3 frame を sample frame PNG として export (320x180 grayscale で十分、Pass 1 と同 resolution)
4. CSV worksheet (`<recording>.csv`) を生成:
    - 列: `index` / `boundary_type` (start/end/gap_start/gap_end) / `timestamp_sec` / `timestamp_display` (HH:MM:SS.fff) / `current_type` (fl_match/unknown/gap) / `brightness_csv_ref` / `sample_frame_png_ref` / `idios_verdict` (空欄、Idios が記入) / `idios_note` (空欄)

**出力**:

- `tests/baselines/v0.3.0/audit-worksheet/<recording>.csv` — pre-screen 結果 worksheet
- `tests/baselines/v0.3.0/audit-worksheet/<recording>/brightness-around-<t>.csv` — 各境界 ±5s
- `tests/baselines/v0.3.0/audit-worksheet/<recording>/frame-around-<t>.png` — sample frame snapshot

### 3.2 Stage 2: Manual viewing (Idios)

**入力**:

- Stage 1 の worksheet CSV
- 元動画 (player で再生: VLC / mpv / Resolve / Idios のお好み)
- 必要に応じて brightness CSV / sample frame PNG

**処理** (Idios manual):

1. worksheet CSV を表計算ツール (Excel / LibreOffice / Numbers) で開く
2. 各 boundary 候補について、player で該当 timestamp ±5s を再生
3. `idios_verdict` 列に判定を記入:
    - `match_start` — 試合の始まり (= 試合境界 start)
    - `match_end` — 試合の終わり (= 試合境界 end)
    - `false_positive` — 試合境界ではない (例: スコアバー誤検出、試合中の暗転)
    - `uncertain` — 画面が暗くて判断不能 / 特殊条件 (後で (c) 既知限界扱い)
4. worksheet にない箇所で「ここに試合境界がある」と気づいた場合は CSV 末尾に行追加 + `current_type=missing` で記入 (= silent miss 候補)
5. 全 boundary について verdict 記入後、`tests/baselines/v0.3.0/ground-truth/<recording>.json` を生成 (worksheet CSV の `match_start` / `match_end` から `matches[]` を組み立て、`vtuber-primary-ground-truth.json` schema 準拠):

   ```json
   {
     "source_file": "20260116/2026-01-16 22-12-57.mkv",
     "source_size_bytes": 39723142336,
     "source_dir_label": "obs-20260116",
     "ground_truth_provider": "user (Idios, manual)",
     "ground_truth_provided_at": "2026-05-19",
     "tolerance_sec": 1,
     "matches": [
       {"index": 1, "start_time": 49, "end_time": 1055, "duration": 1006, "type": "fl_match"},
       ...
     ]
   }
   ```

   - `tolerance_sec` = 1: **Stage 3 `audit-compare.py` が baseline と ground truth を照合する際の許容誤差** (= 「baseline timestamp が ground truth ±1s 以内なら一致」)。Idios の視覚確認精度ではない (視覚確認は player の seek 精度に依存、典型 0.1-0.5s)。issue 本文「±1s (Pass 1 sample interval 内で十分)」と整合。Pass 1 sample interval は 3s だが、A5 borderline extension で sub-sample boundary も検出される現状を踏まえ、より厳しい 1s を採用
   - `start_time` / `end_time` / `duration` は秒単位、整数または小数 (Idios の視覚確認精度に依存、典型 0.1-1s 粒度)
   - `type` は `fl_match` のみ採用 (issue scope では試合境界のみ確定、`unknown` 分類は detector 判断で baseline metadata.json 側に残す)

**出力**:

- `tests/baselines/v0.3.0/ground-truth/<recording>.json` — Idios 確定 ground truth
- (記入済) `tests/baselines/v0.3.0/audit-worksheet/<recording>.csv` — verdict 込み worksheet (audit trail として保持)

### 3.3 Stage 3: Diff & classify (Claude + Idios)

**入力**:

- `tests/baselines/v0.3.0/<recording>.metadata.json` (現 baseline)
- `tests/baselines/v0.3.0/ground-truth/<recording>.json` (Idios 確定)
- 記入済 worksheet CSV

**処理** (`scripts/audit-compare.py` + Idios manual classification):

1. baseline matches[] と ground truth matches[] を `tolerance_sec=1` で照合
2. 以下を抽出:
    - **agreed**: baseline と ground truth で `start_time` / `end_time` が ±1s 一致
    - **silent_miss**: ground truth にあるが baseline にない (start または end)
    - **false_positive**: baseline にあるが ground truth にない (start または end)
    - **boundary_shift**: baseline と ground truth で ±1s を超える timestamp drift (例: 56:07 vs 53:50)
3. 各 finding を §5 rubric で (a/b/c) 分類:
    - Claude が candidate justification (現 detector で再検知した結果 / brightness 証跡) を提示
    - Idios が最終判断
4. (b) 該当 finding を集約 → **3 件以上なら Iron Law 2 bulk confirmation** → 別 issue 一括起票

**出力**:

- `docs/v030-baseline-audit.md` — finding 集約 deliverable (recording 別 section + cross-recording summary)
- (b) 該当 detector tuning 別 issue (0〜N 件、起票時刻と issue # を audit doc に記録)
- (c) 既知限界 P3-low 別 issue (該当があれば、`docs/video-processing.md` "既知の制限" 追記提案を含む)

## 4. Components

### 4.1 新規 scripts

| Path | 役割 |
|---|---|
| `scripts/audit-prepare.py` | Stage 1 worksheet generator。引数: `<recording-label>`、内部で `tests/baselines/v0.3.0/<label>.metadata.json` を読む |
| `scripts/audit-compare.py` | Stage 3 diff extractor。引数: `<recording-label>`、ground truth と baseline を tolerance_sec で照合 |

両 script とも `python scripts/audit-prepare.py <label>` 形式で直接実行 (hyphen 命名、`compare-baseline.py` family と整合)。CLI 引数は最低限 (label のみ) + `--tolerance-sec` / `--worksheet-dir` 等の override option。

### 4.2 新規 files

| Path | 種別 | 生成主 |
|---|---|---|
| `tests/baselines/v0.3.0/ground-truth/<recording>.json` | Idios 確定 ground truth | Idios (worksheet CSV から組立) |
| `tests/baselines/v0.3.0/audit-worksheet/<recording>.csv` | Pre-screen worksheet | Claude (audit-prepare.py) |
| `tests/baselines/v0.3.0/audit-worksheet/<recording>/brightness-around-<t>.csv` | ±5s brightness frame data | Claude (audit-prepare.py) |
| `tests/baselines/v0.3.0/audit-worksheet/<recording>/frame-around-<t>.png` | Sample frame snapshot | Claude (audit-prepare.py) |
| `docs/v030-baseline-audit.md` | Finding 集約 deliverable | Claude + Idios (Stage 3 出力) |

### 4.3 Reused

| Path | 用途 |
|---|---|
| `scripts/compare-baseline.py` (#777) | Diff ロジックの参考 (bit-exact vs tolerance-based の違い) |
| `allaganeye debug-brightness <video>` | Brightness CSV 出力の既存 CLI、内部ロジックを Stage 1 で再利用 |
| `tests/baselines/v0.3.0/vtuber-primary-ground-truth.json` | Ground truth file schema reference |
| `tests/baselines/v0.3.0/<recording>.metadata.json` | 現 baseline (PR #793 head が確定値) |

## 5. Finding classification rubric

各 finding (silent miss / false positive / boundary shift) を以下のいずれかに分類:

| 区分 | 判定 fork | 対応 |
|---|---|---|
| **(a) baseline 修正** | 現 detector で同 timestamp を再検知すると **正検出される (silent_miss → 検出される / false_positive → 検出されない / boundary_shift → ground truth ±1s 以内に収束)**。baseline metadata.json が偶発的に古い / 過去 regenerate 時の non-determinism | `tests/baselines/v0.3.0/<recording>.metadata.json` を regenerate (PR #793 内で消化 or 本 issue の deliverable PR で消化、user 判断) |
| **(b) detector tuning** | 現 detector で再検知しても **miss / FP / drift が再現** する。アルゴリズム改善が必要 (例: sub-sample boundary、scorebar misclassification、audio promotion 偽陽性、boundary_shift が ±1s を超えて drift する場合の精度改善、新規 edge case) | **別 issue 起票** (Iron Law 2 bulk confirm: 3 件以上はまとめて user 確認後に起票)。本 issue は完了させ、tuning 自体は別 issue で別 brainstorming |
| **(c) 既知限界** | 現 detector で再検知しても不検出 / drift が残る、かつ修正方針が立たない (例: 純黒でないローディング画面、特殊 OBS recording setting、ffmpeg version 依存 PTS drift、min_blackout_duration threshold の trade-off で許容するもの) | `docs/v030-baseline-audit.md` に document + `CLAUDE.md` / `docs/video-processing.md` の "既知の制限" に追記 (P3-low 別 issue で実施) |

### 5.1 判断 fork のフローチャート

```text
Finding (silent_miss / false_positive / boundary_shift)
   ↓
現 detector で同 timestamp を再検知 (allaganeye detect <video> + 該当 segment)
   ↓
ground truth と一致? (silent_miss → 検出 / false_positive → 不検出 / boundary_shift → ±1s 以内)
   ├─ Yes ─→ (a) baseline 修正 (baseline metadata.json が古い、regenerate)
   └─ No (再現)
       ↓
       他 detector 設定 (no-audio off, threshold 変更等) で改善余地?
       ├─ Yes ─→ (b) detector tuning (別 issue 起票)
       └─ No
           ↓
           特殊条件 (純黒でない / ffmpeg version 依存 / min_blackout_duration trade-off 等)?
           ├─ Yes ─→ (c) 既知限界
           └─ No ──→ (b) detector tuning (新規 algorithm 検討必要)
```

### 5.2 例: F1 (obs-20260116, t=3227.4, 3.6s blackout)

- baseline (PR #793 後): 検出済 (Match 3 end 53:50)
- ground truth (想定): 検出すべき (実試合境界)
- 現 detector で再検知: 正検出
- → **agreed** (finding なし、本 audit の trigger になった F1 自体は PR #793 で消化済を確認するための regression check)

### 5.3 例: 仮想 finding (obs-20260119, t=1234.5, 0.5s blackout、現 baseline 未検出)

- baseline (PR #793 後): 未検出
- ground truth (Idios 確定): 試合境界
- 現 detector で再検知: 同じく未検出
- → 0.5s は `min_blackout_duration=3.0` 未満なので Pass 1 で除外される設計
- → **(c) 既知限界** (`min_blackout_duration` の 3s threshold を緩めると false positive が増えるトレードオフ。設計判断として現状維持)

## 6. Increment plan

### 6.1 Iteration 1: obs-20260116 (proof of concept)

| Step | 担当 | 所要 |
|---|---|---|
| 1 | `scripts/audit-prepare.py` 試作実装 | Claude | 1-2h |
| 2 | obs-20260116 で worksheet 生成 | Claude | 5-10 分 |
| 3 | obs-20260116 視聴 + ground-truth/obs-20260116.json 作成 | Idios | 1-1.5h (scorebar V2 validated なので最も verify しやすい) |
| 4 | `scripts/audit-compare.py` 試作実装 | Claude | 1-2h |
| 5 | obs-20260116 diff 抽出 + finding 分類 | Claude + Idios | 30 分-1h |
| 6 | Workflow / script / spec の不足を本 spec doc + scripts に feedback | Claude | 30 分-1h |

**Iteration 1 終了条件**:

- obs-20260116 の ground truth が確定
- (a/b/c) finding 分類 example が docs/v030-baseline-audit.md に 1 件以上記載
- script の interface / output format が安定 (Iteration 2 で再実装が不要)

### 6.2 Iteration 2: 残り 4 baseline batch

| Step | 担当 | 所要 |
|---|---|---|
| 1 | Finalized script で 4 件 worksheet 一括生成 | Claude | 30 分-1h (合計、recording ごと 5-15 分) |
| 2 | obs-20260118 / 20260119 / 20260127 / 20260209 視聴 + ground truth 4 件作成 | Idios | 1.5-3h (一気にやる or 分割は Idios 裁量) |
| 3 | 4 件 diff 抽出 + finding 分類 | Claude + Idios | 1-2h |
| 4 | docs/v030-baseline-audit.md cross-recording summary 追加 | Claude | 30 分 |
| 5 | (b) 該当 detector tuning 別 issue 起票 (3 件以上なら Iron Law 2 bulk confirm) | Idios 承認 + Claude 起票 | 30 分-1h |

**Iteration 2 終了条件 = 本 issue 完了条件**:

- 5 baseline の `ground-truth/<recording>.json` 全件揃う
- 全 finding が (a/b/c) のいずれかに分類済
- (b) 該当 0 件 → audit doc に「detector tuning 不要」明記
- (b) 該当 1+ 件 → 別 issue 起票完了 (issue # を audit doc に cross-link)
- (c) 該当 1+ 件 → CLAUDE.md / docs/video-processing.md の "既知の制限" 更新 PR (本 audit deliverable PR とは別 PR、または同 PR に同梱、user 裁量)
- `docs/v030-baseline-audit.md` write & commit 済

### 6.3 reexamination spec への引き継ぎ

本 audit 完了後、別 brainstorming session で `docs/superpowers/specs/2026-05-19-v030-l3-detect-fps-retirement-reexamination-design.md` を作成し、以下を input にして PR #793 の merge / scope reduce / defer / abandon を確定:

- `docs/v030-baseline-audit.md` の finding summary
- (b) 該当別 issue 起票数とその scope
- 5 baseline の ground truth に対する PR #793 の accuracy 評価

## 7. Edge cases

| ケース | 対応 |
|---|---|
| Recording 動画が手元にない | `ALLAGANEYE_SAMPLE_VIDEO_DIR` を確認、欠損なら本 issue を temporarily block (`needs-input` label を付与、Idios が動画手当 / clarification するまで止める) |
| `audit-prepare.py` が一部 recording で fail (例: codec mismatch / corrupted video) | 該当 recording を skip、failure を spec の Limitations に記載、Iteration 1 で発見されたら spec doc に feedback |
| Idios が「画面が暗くて判断不能」「sample frame が小さすぎて判別不能」 | worksheet で `idios_verdict=uncertain`、後で (c) 既知限界に分類。必要なら sample frame を `frame-around-<t>-large.png` (1280x720) で再生成可能にする option を `audit-prepare.py` に追加 |
| Ground truth と baseline で **全く同じ timestamp** だが Idios が「これは試合境界ではない」と判断 | finding として **false positive** に分類 (= (b) detector tuning が default、再検知で正分類されるなら (a) baseline 修正) |
| Audit 中に PR #793 が update (force-push 等) された | PR #793 head の baseline を再 sync (`git fetch && git checkout pr-793-readonly` で baseline metadata.json を再取得) してから audit を続行。Idios の ground truth は invariant (動画自体は変わらない) なので diff 抽出だけ rerun |
| Iteration 1 で script bug を発見、Iteration 2 で再実装が必要になった | spec doc を update、Iteration 1 の ground truth は invariant なので保持、worksheet は再生成 |
| (b) 該当が 0 件で全 finding が (a) または (c) のみ | audit doc に「detector tuning 不要」を明記 + reexamination spec へ。本 issue は (a) PR / (c) doc PR が merge されたら close |
| (b) 該当が 1-2 件 | 個別 issue 起票 (Iron Law 2 bulk confirm 不要、1 件ずつ確認 OK) |
| (b) 該当が 3+ 件 | **Iron Law 2 bulk confirm 必須**: sample 1 件提示 + 「全件 OK / 個別調整 / やめる」3 択で Idios 確認後に起票 |

## 8. Testing

### 8.1 Script unit test (新規)

| Test | 対象 | Fixture |
|---|---|---|
| `tests/test_audit_prepare.py` | `scripts/audit-prepare.py` の worksheet 生成 | 既存 `obs-20260209.metadata.json` (3 matches, short) を input、生成 worksheet の row 数 / 列名 / brightness CSV reference 整合を検証 |
| `tests/test_audit_compare.py` | `scripts/audit-compare.py` の diff 抽出 | Synthesized baseline + ground truth fixture (intentional silent_miss / false_positive / boundary_shift / agreed を含む) で各 case の出力 classification を検証 |

両 test は `pytest -m audit` 等の dedicated marker で分離 (既存 `slow` marker と区別)、CI では運用パイプラインに含めるが、video file は不要 (metadata fixture のみで test 可能)。

### 8.2 Audit doc verification

audit doc `docs/v030-baseline-audit.md` の cross-link 整合を verify:

- (b) finding が 1+ 件で「別 issue 起票」と書かれているなら、起票 issue # が cross-link されていること
- (c) finding が 1+ 件で「docs/video-processing.md 追記」と書かれているなら、対応 PR # が cross-link されていること

これは markdown linter 範疇外 (link が live でも文意整合は別) なので manual review、または将来 audit doc の整合検査 script を追加してもよい (本 issue scope 外)。

### 8.3 PR Pre-flight (Iron Law 6)

audit 完了後の deliverable PR で以下を実行:

- **Path 別自動チェック**: 新規 script は Python なので `ruff check .` / `ruff format --check .` / `pyright` / `pytest`
- **GUI 影響なし**: 本 audit は Python script + docs + JSON file のみ。`gui/` には触らない (skip 可)
- **Step 0**: `gh pr list --search "796" --state open` で並行 PR を hard gate 確認
- **Step 5 `/codex:adversarial-review`**: focus = "audit script の reproducibility + ground truth schema の妥当性 + finding 分類 rubric の網羅性"

### 8.4 実機検証 trigger

本 audit は **GUI / GPU / audio path / 長時間動画 detect** ロジックを変更しない (新規 script のみ追加)。`AskUserQuestion` での実機検証依頼は不要 (Idios の audit 自体が実機操作)。

## 9. Out of scope

| 項目 | 理由 / どこで扱うか |
|---|---|
| **reexamination spec の作成** | audit 完了後の別 brainstorming で `docs/superpowers/specs/2026-05-19-v030-l3-detect-fps-retirement-reexamination-design.md` を新規作成 |
| **PR #793 の merge / defer 判断** | reexamination spec の責務 |
| **(b) 該当 detector tuning の実装** | 起票された別 issue ごとに別 brainstorming |
| **VTuber / Game DVR / 非 OBS baseline の audit** | `vtuber-primary-ground-truth.json` 既存。本 issue は OBS baseline のみ |
| **新しい baseline 追加 / 削除** | #778 で 5 baseline 確定済。本 issue は既存 5 件の ground truth を確立するのみ |
| **`compare-baseline.py` 改修** | 本 audit は独立 script (`audit-compare.py`) で実装、既存 `compare-baseline.py` (#777 bit-exact comparison) は temasuhana なし |
| **CI 統合** | audit script は手動運用 (Idios が起動)。CI で worksheet 自動生成は本 issue scope 外 |

## 10. 受け入れ条件 mapping (issue #796)

| issue #796 受け入れ条件 | 本 spec での対応 |
|---|---|
| Idios が 5 OBS baseline を視覚確認し、試合境界 timestamp を `tests/baselines/v0.3.0/ground-truth/<recording>.txt` に保存 | §3.2 Stage 2 deliverable (`<recording>.json`、issue 本文 `.txt` → `.json` 変更を §2 で採用) |
| 対象 5 件 (obs-20260116/20260118/20260119/20260127/20260209) | §3.1 / §6 全 5 件対応 |
| timestamp 精度 ±1s | §3.2 ground truth file の `tolerance_sec=1` |
| 現 baseline と ground truth の diff を `docs/v030-baseline-audit.md` (新規) に列挙 | §3.3 Stage 3 deliverable |
| F1-F4 が現 detector (v2 + A5) で正しく検出されることを確認 | §3.3 agreed として記録 (§5.2 example 参照) |
| 新規発見の miss / FP を列挙 | §3.3 silent_miss / false_positive / boundary_shift として記録 |
| 各 finding を (a/b/c) 分類 | §5 rubric |
| (b) 該当分は別 issue 起票 (Iron Law 2 適用、3 件以上なら bulk confirmation) | §6.2 Step 5 / §7 (b) 該当 1-2 件 / 3+ 件の場合分け |
| audit 完了後、reexamination spec §4 に audit 結果を追記し、#576 (PR #793) の扱いを最終確定 | **本 spec の scope 外** (§9 / §6.3 引き継ぎ。reexamination spec が未作成のため別 brainstorming) |

## 11. 関連

- 対象 issue: [#796](https://github.com/Idios/kobutachan-allaganeye/issues/796)
- 対象 PR (audit 完了まで保留): [#793](https://github.com/Idios/kobutachan-allaganeye/pull/793) (#576 fps filter retirement)
- 関連 issue:
  - [#576](https://github.com/Idios/kobutachan-allaganeye/issues/576) — detect fps filter 廃止 (PR #793 の元 issue)
  - [#281](https://github.com/Idios/kobutachan-allaganeye/issues/281) — 検出アルゴリズム動作確認済み環境 docs (closed、本 audit はその発展系)
  - [#560](https://github.com/Idios/kobutachan-allaganeye/issues/560) — 20260118 baseline 281s 乖離 (closed、偶発発見を systematic にするのが本 issue)
  - [#778](https://github.com/Idios/kobutachan-allaganeye/issues/778) — v0.3.0 regression baseline 選定 (5 baseline 確定)
  - [#779](https://github.com/Idios/kobutachan-allaganeye/issues/779) — v0.3.0 regression baseline 生成 (現 baseline metadata.json 生成)
- 関連 spec:
  - [`docs/superpowers/specs/2026-05-18-v030-l3-redefinition-design.md`](2026-05-18-v030-l3-redefinition-design.md) — v0.3.0 L3 redefinition + Pillar 3 perf scope
  - PR #793 ブランチ内 `docs/superpowers/specs/2026-05-18-v030-l3-detect-fps-filter-retirement-design.md` — F1-F4 発生箇所
  - (未作成) `docs/superpowers/specs/2026-05-19-v030-l3-detect-fps-retirement-reexamination-design.md` — 本 audit 完了後の別 brainstorming で作成
- 関連 doc:
  - [`tests/baselines/v0.3.0/README.md`](../../../tests/baselines/v0.3.0/README.md) — baseline set 全体方針
  - [`tests/baselines/v0.3.0/vtuber-primary-ground-truth.json`](../../../tests/baselines/v0.3.0/vtuber-primary-ground-truth.json) — ground truth schema reference
  - [`docs/cli-spec.md`](../../../docs/cli-spec.md) — metadata.json schema
