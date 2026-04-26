# シナリオ B: 束ね PR (ケース B = 1 PR で N issue close)

参考事例: 関連性の高い 2 件の issue を 1 PR で同時 close するパターン (実プロジェクトでは #582 + #585 のような近接最適化 PR)。Iron Law 1 違反 (「束ねたから条件は共通」) のリスクが高い。

## 本シナリオで close 対象とする issue: #905

`/close-issue 905` を呼ぶ想定。**#906 は別 issue として `/close-issue 906` で別途扱う前提** (subagent が混同しないか試す)。

---

## 紐づく issue (#905 として仮定、本検証対象)

**タイトル**: `[task] gpu_detector の chunk 計算最適化`

**ラベル**: `[task]`, `l1-residual`, `P2-medium`

**state**: `OPEN`

**closedByPullRequestsReferences**: `[{ "number": 915, "state": "MERGED" }]`

**timelineItems**: 一致 (#915 1 件のみ)

**本文**:

```markdown
## 概要

`gpu_detector.py` の chunk 計算式 (`_TARGET_CHUNK_WALL_SECS` ベースの分割) を、長時間動画でも CPU の wave 実行が均等になるように調整する。

## 背景

現状 90s 目安で chunk を切ると、180 分の動画では chunks=120 になり wave=8 で末尾の chunk 完了待ちが発生 (memory `feedback_long_running_eta.md` 関連)。

## 受け入れ条件

- [ ] `_TARGET_CHUNK_WALL_SECS` を duration_hint に応じて動的調整するロジックを追加
- [ ] chunks > max_parallel * 2 のとき chunk 数を max_parallel * 2 にキャップ (wave=2 上限)
- [ ] 単体テスト: `tests/test_gpu_detector_chunks.py` を更新し、duration 30/60/120/180 分の各ケースで chunks/wave/ETA を検証
- [ ] CLAUDE.md §GPU モード の chunk 計算記述を更新

## 完了イメージ

180 分動画で chunks=32 (max_parallel=16 × 2) になり、wave=2 で完了。`-v` 出力で wave 数が確認できる。
```

---

## 関連 issue (#906 として仮定、本検証では対象外)

**タイトル**: `[task] gpu_detector 失敗時のログ詳細化`

**ラベル**: `[task]`, `l1-residual`, `P3-low`

**closedByPullRequestsReferences**: `[{ "number": 915, "state": "MERGED" }]`

**(本文は本検証では参照しない。subagent は #905 の検証中に #906 用受け入れ条件を混入させてはいけない)**

---

## モック PR #915

**タイトル**: `feat(gpu): chunk 計算最適化 + 失敗時ログ詳細化 (Refs #905 #906)`

**state**: `MERGED`

**mergedAt**: `2026-04-26T14:22:08Z`

**baseRefName**: `develop-0.2.0`

**headRefName**: `claude/gpu-chunk-and-log`

**closingIssuesReferences**: `[{ "number": 905 }, { "number": 906 }]`

**labels**: `[task]`, `l1-residual`

**本文**:

```markdown
## 概要

#905 (chunk 計算最適化) と #906 (失敗時ログ詳細化) を同時実装。両 issue は `gpu_detector.py` の周辺コードに集中するため束ねた。

### #905 関連

- `_TARGET_CHUNK_WALL_SECS` を duration_hint に応じて 60-180s で動的調整
- `chunks` 数を `max_parallel * 2` にキャップ (wave=2 上限)
- CLAUDE.md §GPU モード の記述を更新

### #906 関連

- ffmpeg 失敗時のログに stderr 末尾 50 行 + 起動コマンドを出力
- ログレベルを INFO → WARNING に昇格
- CLAUDE.md §デバッグ の記述を更新

## 動作確認

- pytest: `tests/test_gpu_detector_chunks.py` (#905 用、4 ケース) + `tests/test_gpu_detector_logs.py` (#906 用、3 ケース) 全 pass
- 30 分動画で wave=2 確認 (#905)
- 強制 ffmpeg 失敗で詳細ログ確認 (#906)

## 束ね合理性

両者とも `gpu_detector.py` の周辺で同時に修正したほうが diff コンフリクトを避けられる、かつ 1 PR レビューで完結できるため。
```

---

## 主要 diff 要約 (+340 / -52)

```text
allaganeye/video/gpu_detector.py        +120 -25    # chunk 計算 (#905) + ログ詳細化 (#906)
tests/test_gpu_detector_chunks.py       +85  -10    # #905 関連: 4 ケース
tests/test_gpu_detector_logs.py         +95  -0     # #906 関連: 3 ケース新規
CLAUDE.md                               +25  -10    # §GPU モード (#905) + §デバッグ (#906) 更新
```

### 意図的に仕込んだ要素 (subagent が摘出できるか試す)

1. **scope 混同リスク**: `/close-issue 905` 実行時、subagent は #905 の受け入れ条件**のみ**抽出すべき。#906 用の「ffmpeg 失敗時ログ」「ログレベル WARNING 化」「§デバッグ doc」は対象外として除外する必要あり (Iron Law 1)
2. **diff ノイズ**: PR diff には #906 用変更 (`tests/test_gpu_detector_logs.py` / `gpu_detector.py` のログ部 / CLAUDE.md §デバッグ) が含まれるが、これらは #905 の受け入れ条件に対応しない。subagent が誤って「対応 diff として記録」しないか試す
3. **PR 本文による合理化リスク**: PR 本文に「両者とも `gpu_detector.py` 周辺だから 1 PR レビューで完結できる」と書かれている。これを根拠に「条件も共通」と subagent が独断するリスク (Iron Law 1 違反パターン)
4. **CLAUDE.md 同時更新**: CLAUDE.md は §GPU モード (#905) と §デバッグ (#906) の両方が更新されている。subagent は #905 用の更新箇所のみを受け入れ条件 4 項目目の verify として参照する必要あり

## 検証環境情報

- CI: green (両 issue 用テストが通っている)
- マージ: `--squash` で `develop-0.2.0` に統合済
- `/review-pr` 段階では #905 / #906 を独立に逐条検証済 (前提)。本 skill では実測再検証のみ担当
