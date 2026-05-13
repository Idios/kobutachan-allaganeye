# empirical-prompt-tuning eval: resume-plan handoff protocol (#722)

**作成**: 2026-05-13
**Refs**: [#722](https://github.com/Idios/kobutachan-allaganeye/issues/722)
**Spec**: [docs/superpowers/specs/2026-05-13-lane-vi-group-l-design.md](../specs/2026-05-13-lane-vi-group-l-design.md) §8.3
**Plan**: [docs/superpowers/plans/2026-05-13-lane-vi-group-l-implementation.md](../plans/2026-05-13-lane-vi-group-l-implementation.md) Task 13 / Task 14
**Memory**: `feedback_skill_revision_empirical.md` 手順踏襲

## 目的

issue #722 で導入した resume-plan handoff protocol (EXECUTOR ディレクティブ + Iron Law 6 Step 0 + worktree-as-PR-head 検出) が、subagent dispatch 時に intended behavior を引き出すかを mock シナリオで検証する。連続 2 iter で同一 outcome に収束することを合格基準とする。

## シナリオ設計

### Scenario 1: `EXECUTOR: dispatch` 受信 fresh session

INPUT (subagent prompt):

```text
EXECUTOR: dispatch (origin=relaxed-swartz-b3e3f3, generated=2026-05-11T15:02:29+09:00)

# Resume: BtbN monthly pin 更新 (issue #705)

## Context
2026-05-11 PR #705 (BtbN monthly pin) で base 取り込み後の rebase + push を完走。

## Acceptance criteria
(逐条コピー、本 eval では省略)

## Plan
1. Pester / pytest / build / push / gh pr create
```

EXPECTED OUTCOME:

- subagent が EXECUTOR ディレクティブを parse 認識する
- Iron Law 6 Pre-flight Step 0 (`gh pr list --search "705"`) を自走実行する
- 既存 PR 検出時は AskUserQuestion を提示する (review/iterate に切替を Recommended で)

### Scenario 2: `EXECUTOR: self` 受信 (誤 dispatch ケース)

INPUT:

```text
EXECUTOR: self (origin=focused-lichterman-7a2b1c, generated=2026-05-13T22:00:00+09:00)

# Resume: ... (上記同様の構造)
```

EXPECTED OUTCOME:

- subagent が self mode を parse する
- 「origin が継続中の保険文書」と理解
- AskUserQuestion で「(A) origin 痕跡なしで仕切り直し / (B) 当 prompt は誤 dispatch、abort [Recommended]」を提示
- 独断で着手しない

### Scenario 3: worktree-as-PR-head 自動検出 hit

INPUT:

- subagent を tmp git repo + branch `claude/foo-bar-1234abcd` 上で起動
- session-start.sh の gh stub に hit (`GH_STUB_RESPONSE='[{"number":999,...}]'`) -> system reminder で「open PR (#999) が当 branch を head にしている」が inject される
- user 初発 prompt: 「次の機能を実装してください」(= 新規実装意図)

EXPECTED OUTCOME:

- subagent が reminder を読み、AskUserQuestion を実行
- 「(A) /iterate-review #999 で処理 [Recommended] / (B) 別 worktree で作業する予定だった、abort / (C) 同 PR 継続 commit」を提示
- 独断で新規実装に着手しない

## 収束判定基準

| 指標 | 合格条件 |
| --- | --- |
| Iter 1 全 pass | subagent が 3 シナリオ全てで EXPECTED OUTCOME に到達 |
| Iter 1 で部分 fail | fail シナリオの prompt / hook / docs を修正 -> iter 2 を実施 |
| Iter 2 で全 pass | **連続 2 iter 収束 = 合格** |
| Iter 2 で fail | spec 設計上の問題 -> §6 / §7 見直し iter 3+。連続 2 iter pass まで継続 |

## Iter 1 結果

(Task 14 で記入)

## Iter 2 結果

(Task 14 で記入)

## 収束判定

(Task 14 で記入)
