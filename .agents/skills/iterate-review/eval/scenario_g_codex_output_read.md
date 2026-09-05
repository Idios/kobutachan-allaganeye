# シナリオ G: codex_output_read (#949 Codex 出力の読み取り / subagent 申告)

`/iterate-review` Step 2.1 prompt template item 8 + Step 2.2 validation 6 + Step 4 Final summary の
`## Codex 出力読み取り` 節を対象とする EPT シナリオ。review-pr 側の 2 本は
[`../../review-pr/eval/scenario_g_codex_output_read.md`](../../review-pr/eval/scenario_g_codex_output_read.md) を参照。

## G-3 (edge): Codex review 非起動の Round を subagent が申告する

### 想定状況

executor は `/iterate-review` が Step 2.1 で dispatch した review subagent である。
PR `#<N>` は touched 4 file / diff 60 line の doc-only PR で、`/review-pr` Step 5a の
Codex review 起動条件 3 つ (条件1 大規模 / 条件2 再発 root cause 複数 / 条件3 core 変更対象ファイル) の**いずれにも該当しない**。
Round 2 の final message を prompt template item 7 の構造で組み立てる直前の地点にいる。

### 期待挙動

Codex を起動していない Round でも `## meta` の申告行を省略しない。省略すると controller の
Step 2.2 validation が parse error として再 dispatch する。

### 要件チェックリスト

1. **[critical]** `## meta` に Codex 出力読み取りの状態行が含まれている
2. **[critical]** 非起動であることが理由付きで書かれている (空欄 / 省略 / 理由なしではない)
3. controller 側の Step 2.2 validation で何が parse error になるかを説明している
4. その申告が Step 4 Final summary へ転記される旨に触れている
5. Codex fallback notice とは別行 / 別セクションであることを区別している
