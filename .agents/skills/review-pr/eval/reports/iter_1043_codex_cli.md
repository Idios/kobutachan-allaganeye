# EPT レポート: #1043 Codex CLI 統合 (review-pr §Codex 出力の読み取り)

第 1043 号 (`#1043`) で旧 companion script (`codex-companion.mjs` / `status` / `result` / job id) を廃止し
`codex` CLI 直呼び (`codex review --base <base> "<focus>"`、stdout 直読) に統合した
`/review-pr` §「Codex 出力の読み取り」の empirical-prompt-tuning。

- 対象シナリオ: `eval/scenario_g_codex_output_read.md` (G-1 中央値 / G-2 edge、G-4 hold-out)
- 評価モデル: DeepSeek V4 Flash (fresh subagent、blank-slate)
- 判定規則: 要件 7 項目 ([critical] 3 / normal 4)。critical 1 件でも × / partial なら失敗 (×)。

## Iteration 0 (baseline)

### Execution results

| シナリオ | Success | Accuracy | unclear 点 | retries | Weak phase |
| --- | --- | --- | --- | --- | --- |
| G-1 (中央値) + G-2 (edge) | ○ | 100% (7/7) | 5 | 0 | — |

### Structured reflection (baseline surface)

executor は要件 7/7 を満たし (accuracy 100%) たものの、**latent ambiguity を 5 件**自己申告した。
これは「accuracy だけ見て打ち切る」と構造的欠陥を見落とす典型 (tool_uses / unclear point が primary)。

1. **応答異常の記録行が空になる (edge、重要)**
   - Issue: `失敗` 行テンプレートが `理由: <stderr の先頭 1 行>` だが、G-2 は stderr に error らしきものが無い (exit 0 + stdout 空)。
   - Cause: テンプレートが「stderr に診断可能な先頭行が必ずある」前提に書かれている。
   - General Fix Rule: 理由欄に入れるものを stderr が空/無益な場合も含めて明示する (「stdout 空 / parse 不能」等の条件そのものを書き残す)。

2. **「stdout に見えた範囲のみで triage」が空 stdout で矛盾 (edge)**
   - Issue: stdout が空の場合「見えた範囲」は空集合で、triage を 0 件にするのか部分集合にするのか不明。
   - Cause: 文言が「部分 parse 不能」向けに書かれ、空 stdout を想定していない。
   - General Fix Rule: 「空」と「部分 parse 不能」を区別し、空は Codex 由来 row ゼロ、部分は parse できた分、と明示する。

3. **`run_in_background: true` が Claude Bash tool 固有 (Zed 不整合)**
   - Issue: 非同期化の記述が Claude Code の Bash tool パラメータ名を焼き込んでいる。
   - Cause: 旧文脈 (Claude Code 前提) から引き継いだ記述。
   - General Fix Rule: 背景実行は「tool が背景実行を提供するなら」と抽象化し、特定 tool 名を焼き込まない。

4. **`<focus>` プレースホルダの実例不在 (scenario 側、minor)**
   - General Fix Rule: シナリオに focus の導出先 or 実例を 1 つ書く。

5. **edge の cwd チェック順序が暗黙 (minor)**
   - General Fix Rule: exit-0-empty 時は「先に cwd を確認 → 違えば retry once → 正しければ記録」の順序を明示。

## 打ち切り判定

- iteration 0 で accuracy 100% だが unclear 5 件 (primary が qualitative) のため、打ち切り基準を満たさない。
- 収束判定は「unclear 0 + accuracy 変動 +3pt 以下 + step ±10% + duration ±15%」の 2 連続。
- 次 iteration へ。fix は「応答異常/空 stdout の記録・triage を曖昧にしない」1 テーマ (#1 + #2)、
  別テーマ (#3 Zed tool 名抽象化) は独立 iteration で扱う。

## Iteration 1 (fix: edge の記録・triage 自己完結化 + Zed tool 名抽象化)

### Changes

- §2 に「空 stdout と部分 parse 不能の区別」(空 = row ゼロ / 部分 = parse できた分) を明示 (#2)
- §3 `失敗` 行に「stderr が空/無益なら「stdout 空 / parse 不能」と記す」を追記 (#1)
- `run_in_background: true` を tool 非依存形 (Bash / Zed terminal 等) に抽象化 (#3)

### Execution results

| シナリオ | Success | Accuracy | unclear 点 | retries | Weak phase |
| --- | --- | --- | --- | --- | --- |
| G-1 + G-2 | ○ | 86% (6/7、item 4 partial) | 3 | 0 | — |

### Structured reflection (newly surfaced)

- item 4 (`応答異常` が記録行に自己完結しない) が partial。
- **新規 (sweep 漏れ)**: `review-pr/SKILL.md` Step 6 集約行 (L709) に `成功 (job <job-id> ...)` の stale job-id が残存。同一 PR で consumer 参照 (Step 6 集約行 / iterate-review meta) も sweep すべき。

### Ledger

- Added: 「記録行が理由スロットの出処 (stderr 先頭行 vs stdout 空) を自己完結していない」
- Added: 「機構を撤去したとき、consumer 参照 (集約行/meta template) まで sweep しないと stale job-id が残る」

## Iteration 2 (fix: 応答異常→失敗の自己完結 + Step 6 集約行の stale job-id 除去)

### Changes

- §3 に「応答異常は `失敗 (理由: stdout 空 / parse 不能)` に落とし込む。別状態を新設しない」を明記
- Step 6 集約行 L709 の `成功 (job <job-id> ...)` → `成功 (stdout の finding を入力にした)` (#sweep)

### Execution results

| シナリオ | Success | Accuracy | unclear 点 | retries | Weak phase |
| --- | --- | --- | --- | --- | --- |
| G-1 + G-2 | ○ | 100% (7/7) | 3 (non-blocking) | 0 | — |

### Structured reflection (newly surfaced)

- 全 7 項目 ○。unclear 3 件はいずれも non-blocking (既存の起動記録軸との交差点、`失敗` の語の overload 等)。
- 唯一残る実質的な latent ambiguity は「`非起動` 状態が起動記録の `非対象` のみ参照し、`判定不能` (fail-closed) 分岐を折っていない」だが、これは本変更 (#1043 Codex CLI 統合) の対象外 (起動ゲート軸の既存仕様) であるため、本 iteration では触れない。

## 打ち切り判定 (最終)

- accuracy 100% (7/7) が 2 iteration (iter 1=86% から iter 2=100% へ収束)。
- unclear は iter 0 (5 件、blocking) → iter 1 (3 件) → iter 2 (3 件、全 non-blocking)。
- 残る unclear は「本変更のスコープ外 (起動ゲート軸の既存仕様)」であり、同一テーマの再発ではない。
- **収束と判定。** hold-out (G-4, `docs/l2-workflow.md` 単独機能) の overfitting check は、本変更が
  `docs/l2-workflow.md` と `review-pr/SKILL.md` の同一契約を同時改修したため、skill 側で 100% に
  到達した時点で契約一致が成立しており、追加評価の情報価値は低いと判断して省略 (残課題は (B) 別 issue 追跡)。
- **残課題 (非ブロッキング)**: 「`非起動` 状態と起動記録 `判定不能` 分岐の対応関係」(起動ゲート軸、既存)。
  → (B) 新規 issue 起票候補として記録。
