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

## Iter 1 (baseline、5 scenarios fresh subagent dispatch)

全 5 scenarios で [critical] 全 ○ 達成。詳細は `empirical-tuning-iter1.md` 参照。

新規 unclear point (SKILL.md actionable):

- **A-UP1: label 存在 pre-check 不在**
  - Issue: A scenario で `--label "l1-cli"` を指定するが、GitHub repo に当該ラベルが存在するか未確認
  - Cause: SKILL.md 手順 4 (重複チェック) と 手順 6 (gh issue create) の間に label 存在確認 step がない
  - General Fix Rule: scope/優先度 label を `--label` 指定する前に `gh label list | grep <label>` で存在確認、未作成なら `gh label create` を先行する
  - Status: Iter 2 fix 適用済

非 actionable (workflow success / mock issue): C-UP2 (#125 dup 検出), D 重複 (#742 検出), E-UP1 (mock severity 不整合)。

## Iter 2 (Iter 1 の A-UP1 fix + hold-out 検証)

Fix: SKILL.md 手順 4 を「重複チェック + label 存在確認」に拡張。`gh label list | grep` 検証を追加。1 line 修正。

Mizchi 規範 (2 consecutive clears) の strict 適用には 5 scenarios の再 dispatch が必要だが、Resource cutoff 認容により skip。代わりに hold-out 1 scenario (F) で overfitting check 実施。

## Patterns

| Pattern name | Example | General Fix Rule | Seen in |
|---|---|---|---|
| label-pre-check-missing | "--label 指定前に gh label list で存在確認していない" | scope/優先度 label を指定する前に gh label list で存在確認、未作成なら gh label create を先行 | iter 1 (A-UP1) |
