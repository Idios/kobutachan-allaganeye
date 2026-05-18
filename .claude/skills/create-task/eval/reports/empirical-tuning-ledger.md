# create-task SKILL.md empirical-prompt-tuning ledger

iter ごとに pattern を累積する。同じ `General Fix Rule` が再出現したら "Seen in" を update して、既存 fix が prevent しなかった理由を記録する。

protocol 参考: <https://github.com/mizchi/skills/tree/main/empirical-prompt-tuning>
session-id: eloquent-kalam-0196f5

## Iter 0 (description / body 整合性 static check)

- Issue: frontmatter `description` が "全 prefix 対応" のみで、refactor/task/risk preamble (期待値 / 現状 / ユーザー影響・重要性) 必須化を signal していない
- Cause: Task 7 commit b19bf47 は body (手順 3 / 5 / 注意事項) のみ改訂、frontmatter description は据え置きだった
- General Fix Rule: skill 改修で body の semantic を変えた場合、frontmatter description にも変更点を反映する (description は subagent が body 解釈の前提として使うため、gap があると false positive が出る)
- Seen in: Iter 0
- Status: 解消済 (description に "refactor/task/risk は preamble 必須" を明記)

## Patterns

(iter 1 以降で追加)
