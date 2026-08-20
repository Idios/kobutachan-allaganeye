# シナリオ G: codex_output_read (#949 Codex 出力の読み取り)

`/review-pr` Step 5a に新設した §「Codex 出力の読み取り」を対象とする EPT シナリオ。
中央値 1 (G-1) + edge 1 (G-2) の 2 本立て。iterate-review 側の edge は
[`../../iterate-review/eval/scenario_g_codex_output_read.md`](../../iterate-review/eval/scenario_g_codex_output_read.md) を参照。

## G-1 (中央値): Codex review が正常完了したあとの finding 取り込み

### 想定状況

PR `#<N>` は `allaganeye/video/detector.py` の core ロジック変更を含み、`/review-pr` Step 5a の
Codex review 起動条件 (L1 core ロジック変更) に該当する。tier 1 = companion script 直接呼び出しで
`codex-companion.mjs review --base develop-0.3.1` を Bash 実行し、**exit code 0 で完了した**。
executor は Step 5b トリアージ表へ finding を統合する直前の地点にいる。

### 期待挙動

review 実行の stdout をそのまま finding の入力にせず、保存済み全文を読み直してから統合する。

### 要件チェックリスト

1. **[critical]** finding の取り込み元が、review を実行した Bash の stdout **ではなく**保存済み全文であることが deliverable から判る
2. **[critical]** 保存済み全文を得る具体的な command が 1 本示され、そのまま実行できる形になっている (プレースホルダのみで終わっていない)
3. その command を実行する cwd の制約に言及している
4. job-id を指定するか省略するかの判断と、その理由が示されている
5. 依存する plugin の version が併記されている
6. Step 5b トリアージ表への統合 (出所の記載) に触れている

## G-2 (edge): 保存済み出力の読み取りに失敗した

### 想定状況

G-1 と同じ状況だが、保存済み全文を読む command が **exit code 1** と
`No finished Codex jobs found for this repository yet.` を返した。
Codex review 自体は exit 0 で完了しており、stdout には review 本文の一部が見えている。

### 期待挙動

読み取り失敗は Codex CLI の failure ではないため fallback へ倒さない。
stdout の範囲で triage したうえで、読めなかった事実と理由を記録する。

### 要件チェックリスト

1. **[critical]** superpowers `requesting-code-review` fallback を起動していない (読み取り失敗を Codex fail と区別している)
2. **[critical]** Step 6 レビュー報告に記録する 1 行を、理由込みの具体文として出している
3. その 1 行が Codex fallback notice とは別物である旨を区別している
4. stdout に見えた範囲のみで triage した事実を明示している
5. 記録義務が必要な理由 (何が事後に区別できなくなるか) に言及している
