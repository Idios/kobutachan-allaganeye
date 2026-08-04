# EPT 再評価: #854 Codex slash-invoke 記述の 3-tier 整合 (iterate-review)

対象 diff: SKILL.md L63 (Step 2.1 blockquote の Codex fallback 記述) / L335 (Codex fallback notice 前置き) の slash 表記 → companion script (tier 1) 表記への整合。eval/requirements.md シナリオ J narrative も同期。

## Iteration 0 (description / body consistency)

frontmatter description は無変更。body 変更は既存節内の invocation path 用語整合のみで、description が主張する trigger / scope に影響なし。gap なし。

## Iteration 1 (シナリオ J、fresh subagent、model: sonnet)

| 指標 | 値 |
| --- | --- |
| Success | ○ (全 [critical] J-1〜J-5 ○) |
| Accuracy | 100% (5/5) |
| tool_uses | 5 |
| duration_ms | 93,310 |
| Retry count | 0 |

executor は Codex 実行手段を tier 1 = companion script (`codex-companion.mjs review` の Bash 実行) と正しく特定し、slash `/codex:review` を「`disable-model-invocation: true` のため Idios 専用 tier 3」と区別した (本改修の狙いを新規 unclear なく通過)。

> **J-6 条文 (dispatch 時に narrative として検証した追加観点、non-critical)**: 「Codex 実行手段を tier 1 = companion script (`codex-companion.mjs review` の Bash 実行) と特定し、slash `/codex:review` を agent 自身が invoke する計画にしない」。観察結果: ○ (上記 prose の通り、executor は tier 1 特定 + tier 3 区別を正しく実行)。J-6 条文は評価完了後に requirements.md シナリオ J へ non-critical として永続化済み (2026-07-07 /iterate-review Round 追記)。

## Unclear points と処置

本改修 (3-tier 整合) 起因の unclear point は 0。残 2 件はいずれも既存構造由来:

1. HARD-GATE 本文が外部 doc 参照 (executor 自身が「隣接配置済みのため change 不要」と判定) → 対応不要
2. eval requirements J-4 の「Round summary comment (Step 4)」という表現が Step 2.3 (per-round) と Step 4 (final) のどちらを指すか紛らわしい → 既存 eval 文言の細部。#856 で追跡

## 収束判定

構造的欠陥 (agent が実行不可能な slash invoke を前提とする記述) は解消。改修起因 unclear 0 + 全 [critical] ○ のため、`docs/l2-workflow.md` §skill 改修ワークフロー How to apply 6 の「構造的欠陥 (新節欠落 / 判定基準不在レベル) が解消された時点で打ち切り可。残る細部不明瞭点は deferred issue として追跡」を適用し打ち切り (本件の欠陥 = agent が実行不可能な slash invoke を必須 gate の実行手段として規定 は「判定基準不在レベル」相当と判断)。
