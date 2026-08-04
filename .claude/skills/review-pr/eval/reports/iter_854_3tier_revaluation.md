# EPT 再評価: #854 Codex slash-invoke 記述の 3-tier 整合 (review-pr)

対象 diff: SKILL.md Step 5a「optional Codex review (C3)」節の slash 表記 → companion script (tier 1) 表記への整合。eval/requirements.md シナリオ I narrative / H-4 の表記も同期。

## Iteration 0 (description / body consistency)

frontmatter description は無変更。body 変更は Step 5a 節内の invocation path 用語整合のみ。gap なし。

## Iteration 1 (シナリオ I + 追加観点 I-6、fresh subagent、model: sonnet)

> **I-6 条文 (dispatch 時に事前固定した追加観点、non-critical)**: 「Codex review の実行手段を companion script (`codex-companion.mjs review --base ...` の Bash 実行) と正しく特定し、slash command `/codex:review` を agent 自身が invoke する前提にしない」。requirements.md シナリオ I (I-1〜I-5、[critical] 指定は変更せず) への追加は行わず、本改修の検証観点として dispatch prompt 側で固定した (事後の checklist 変更を避けるため report に条文を記録)。
>
> 追記 (2026-07-07 /iterate-review Round): 上記「requirements.md への追加は行わず」は dispatch 当時の判断。評価完了後、I-6 は requirements.md シナリオ I に non-critical として永続化済み (P-1〜P-4 = シナリオ P / J-6 も同時永続化。将来の EPT 再評価の regression 検知用)。

| 指標 | 値 |
| --- | --- |
| Success | ○ (全 [critical] I-1〜I-5 ○、追加 I-6 も ○) |
| Accuracy | 100% (6/6) |
| tool_uses | 6 |
| duration_ms | 105,190 |
| Retry count | 1 (completed 済み mock agent への TaskStop 空振り。判断のやり直しではない) |

executor は C6 検出 (429 → token 枯渇) / 重要 PR 判定 → AskUserQuestion 3 択 / fallback 起動 / Codex fallback notice 全文記載を正しく実行し、tier 1 を companion script の Bash 実行、slash `/codex:review` を Idios 専用 tier 3 と区別した。

## Unclear points と処置

本改修起因の unclear point は 0。残 1 件は既存文言由来:

1. §5a fallback 手順 step 2 (重要 PR 判定) と step 3/4 (「重要 PR でない」限定付き自動 fallback) の優先順が逐語読みで一瞬曖昧 (executor は正しく step 2 優先で実行) → 既存文言の細部。#856 で追跡

## 収束判定

構造的欠陥 (agent が実行不可能な slash invoke を前提とする記述) は解消。改修起因 unclear 0 + 全 [critical] ○ のため、`docs/l2-workflow.md` §skill 改修ワークフロー How to apply 6 の早期打ち切り条項を適用。

## 参考: session-start.sh (Iron Law 6 Pre-flight Step 5) 側の同時評価

同 PR で改修した hook 文言は ad-hoc シナリオ (P-1〜P-4、[critical] = P-1/P-2、dispatch 時に事前固定) で別 executor により評価: Success ○ / Accuracy 100% (4/4) / tool_uses 4 / duration 47,103ms / Retry 0。executor は tier 1 コマンド文字列を正しく構成し、slash は tier 3 (Idios 専用) として plan から除外した。unclear 1 件 (`CLAUDE_PLUGIN_ROOT` の `<version>` placeholder が実行時解決前提) は l2-workflow.md の既存例示由来 → #856 で追跡。

> **P-1〜P-4 条文**: P-1 [critical]「Step 5 の実行手段を companion script 直接呼び出し (tier 1、`codex-companion.mjs adversarial-review`) と特定し、slash `/codex:adversarial-review` を agent 自身が invoke する計画にしない」/ P-2 [critical]「focus 文字列に project 固有焦点 (Iron Law 3 scope creep / encoding boundary / GPU fallback / 同 issue 過去 PR root cause) を含める」/ P-3「invocation path の詳細参照先として docs/l2-workflow.md §Step 5 の invocation path (3-tier、#795) に到達する」/ P-4「Codex CLI fail 時は tier 2 fallback (C6) の存在を認識し、fallback 時は Codex fallback notice 記載が必要と述べる」。
