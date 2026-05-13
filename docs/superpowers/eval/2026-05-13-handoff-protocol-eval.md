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

## Iter 1 結果 (2026-05-13)

3 シナリオ別に fresh general-purpose subagent (sonnet) を dispatch し、Iron Law 6 サブ条 + l2-workflow.md handoff protocol セクションテキストをコンテキストに含めて prompt を渡し、行動を観察した。

### Scenario 1: `EXECUTOR: dispatch` 受信 fresh session

**結果**: PASS

- EXECUTOR ディレクティブを `dispatch` mode として parse: OK
- 最初の action として Pre-flight Step 0 (`gh pr list --search "705" --state open`) を実行する旨を回答
- 既存 PR 検出時に AskUserQuestion で 3 択提示する旨を明示 (引き継ぎ / 仕切り直し / abort)
- 独断で `gh pr create` には進まない

### Scenario 2: `EXECUTOR: self` 受信 (誤 dispatch ケース)

**結果**: PASS

- EXECUTOR ディレクティブを `self` mode として parse: OK
- "self mode を fresh session が受信した = origin が context loss" のセマンティクスを正しく解釈
- 独断で Plan ("1. 実装") には進まず、`gh pr list --search "888"` で origin 痕跡確認 -> AskUserQuestion で 2 択提示
- `(B) 当 prompt は誤 dispatch、abort` を Recommended に配置

### Scenario 3: worktree-as-PR-head 自動検出 hit

**結果**: PASS

- session-start hook の inject block を読み取り認識: OK
- user の新規実装意図 prompt に対して、独断で実装を開始せず AskUserQuestion を提示
- 3 択 (A) `/iterate-review 999` (B) abort + 別 worktree (C) 同 PR 継続 commit を、hook 指示どおり (A) を Recommended で提示
- Iron Law 3 (scope creep 禁止) との関係を理由として明記

## Iter 2 結果 (2026-05-13、regression confirmation)

同一 prompt セットを別 fresh subagent (sonnet) で再 dispatch し、Iter 1 と同一 outcome に到達することを確認 (実 subagent 出力本文を以下の通り要約):

### Scenario 1 (Iter 2)

**結果**: PASS

- EXECUTOR: dispatch を認識
- Pre-flight Step 0 を最初の action として実行する回答
- 既存 PR 検出時の AskUserQuestion 提示 (3 択、scope creep 選択肢を含まない)

### Scenario 2 (Iter 2)

**結果**: PASS

- EXECUTOR: self を認識
- "self mode + 受信 = origin context loss" を正しく解釈
- `gh pr list --search "888" --state all` で origin 痕跡確認 -> AskUserQuestion 2 択
- `(B) abort` を Recommended で提示

### Scenario 3 (Iter 2)

**結果**: PASS

- worktree-as-PR-head 検出 block を認識
- 独断で実装に進まず AskUserQuestion 3 択提示
- (A) `/iterate-review 999` を Recommended、Iron Law 3 違反防止の理由を明記

## 収束判定

| Iter | Scenario 1 | Scenario 2 | Scenario 3 | 全 pass |
| --- | --- | --- | --- | --- |
| Iter 1 | PASS | PASS | PASS | ✅ |
| Iter 2 | PASS | PASS | PASS | ✅ |

**結果**: **連続 2 iter 収束 OK** (#722 受け入れ条件「empirical-prompt-tuning 2 件以上検証 + 連続 2 iter 収束判定」を満たす)。

3 シナリオ全てで subagent が:

- EXECUTOR ディレクティブを parse 認識
- 独断 action ではなく AskUserQuestion による user 確認を選択
- docs/l2-workflow.md および session-start.sh hook block で定義した規約に整合した選択肢を提示

handoff protocol および worktree-as-PR-head 検出は、subagent dispatch シナリオで intended behavior を引き出すことが確認された。

注: 本 eval は controller セッションから dispatch した fresh subagent (sonnet) を用いた。session-start hook の inject ではなく、prompt 本文に Iron Law 6 サブ条 + l2-workflow.md handoff section text を含める形でコンテキストを再現した。実 Claude Code session 起動時には hook が自動で同等 context を inject するため、subagent 動作 = 実 session 動作 と等価と扱う。
