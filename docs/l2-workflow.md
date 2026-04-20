# L2 開発ワークフロー

L1 で運用した「マルチセッション・ロール方式」 (director / lead-engineer / engineer / tester を別 worktree で並走) を廃止し、L2 では**単一ワークツリー + skill ベースディスパッチ**に移行する。

## 背景

L1 のロール方式は単一スコープ (試合分割) では機能したが、L2 の 3 スコープ並行開発 (GUI / インストーラ / guard 統合) では以下の問題が顕在化する:

- 4 セッション × 3 スコープ = 12 ワークツリーとなり、ブランチ・コンフリクト管理が困難
- ロール切り替え (`/assume-role`) の摩擦コストがセッション間往復で増える
- #367 で顕在化した PR 不完全修正問題は、レビュー受け入れ基準が言語化されていなかったことが根本原因
- 他 Anthropic ベストプラクティス (code.claude.com/docs/en/best-practices) は「単一セッション + 明確な計画」を推奨

## アーキテクチャ

### 単一ワークツリー + skill ディスパッチ

```
E:/projects/kobutachan-tools/kobutachan-allaganeye/  ← 唯一の worktree (main or develop-x.x.x)
    ├── .claude/skills/              ← タスク種別ごとの skill
    │   ├── plan/                    ← 計画立案 (grill-me 的)
    │   ├── implement/               ← 実装タスク
    │   ├── test-pr/                 ← PR テスト検証
    │   ├── review-pr/               ← PR レビュー (#367 対策強化版)
    │   ├── create-task/             ← issue 起票
    │   └── release/                 ← リリース作業
    └── docs/knowledge/              ← セッション横断の知見蓄積
```

ユーザーは**単一セッション**で作業し、タスクに応じて `/plan`, `/implement`, `/review-pr` 等を呼び分ける。`AskUserQuestion` でスコープや方針を確認し、`spawn_task` や Agent 呼び出しで独立した調査・実装を並列化する。

### 3 スコープ並行開発のブランチ戦略

L2 は `develop-0.2.0` を統合先とする。3 スコープは**単一ブランチの統合**で運用する:

```
main (リリースタグのみ)
 └── develop-0.2.0 (L2 統合先)
      ├── claude/l2-gui-*            ← GUI 関連作業ブランチ (#105 子)
      ├── claude/l2-installer-*      ← インストーラ作業 (#106 子)
      ├── claude/l2-guard-*          ← guard 統合 (#N1-N7)
      ├── claude/l2-workflow-*       ← L2-0 プロセス系
      └── claude/l1-residual-*       ← L1 残課題消化 (#412-#440)
```

**ブランチ命名規則**: `claude/<scope>-<short-description>` または `claude/<issue-N>-<slug>`

**PR ベース**: 全て `develop-0.2.0`。作業ブランチ間の依存は rebase で解消し、`develop-0.2.0` マージ前に最新状態に揃える。

**リリース時**: `develop-0.2.0 → main` をマージ → `v0.2.0` タグ。

## skill 一覧と責務

旧ロール (director/lead-engineer/engineer/tester) に対応する機能を skill に再構成する。粒度は「タスク種別ごと」で、役割ではなくアクションで分ける。

| skill | 旧ロール対応 | 責務 |
|---|---|---|
| `/plan` | director + lead-engineer | タスクの分解、リスク・曖昧点の事前洗い出し (grill-me)、実装前の計画合意 |
| `/implement` | engineer | 実装 + unit/integration テスト + PR 作成。スコープ逸脱時は `/plan` に戻る |
| `/review-pr` | lead-engineer | PR レビュー + #367 受け入れ基準チェックリスト検証 + マージ判断 |
| `/test-pr` | tester | PR の実機テスト (UX、長時間動画、GPU mode 等)、結果を PR コメントで報告 |
| `/create-task` | director + lead-engineer | issue 起票 (定型テンプレート適用) |
| `/release` | director | リリースタグ、CHANGELOG、main へのマージ |

旧ロールが持っていた「権限境界」(engineer は close 禁止、tester は コード変更禁止等) は**人間 = ユーザーが判断**する責任に戻す。Claude は skill 実行時に `AskUserQuestion` で曖昧点をユーザーに確認する。

## レビュー受け入れ基準 (#367 対策)

PR #343 のような「複数 Issue が不完全修正のままクローズされる」事故を防ぐため、`/review-pr` skill は以下を自動検証する:

### 検証項目 (マージ前必須)

- [ ] **受け入れ条件の全項目が満たされているか**: 元 issue の `## 受け入れ条件` チェックボックスを PR 本文で反映、テストで検証
- [ ] **実装内容が PR 説明と一致しているか**: 変更差分と PR body の乖離検出
- [ ] **テスト存在**: 変更行に対応する test ケースがあるか (contract test + baseline FAIL 検証)
- [ ] **UI/出力変更の実証**: CLI 出力・GUI スクリーンショット等の実サンプルを PR 本文に添付
- [ ] **複数 issue 束ね時の合理性**: 1 PR で複数 issue を閉じる場合、束ねる理由を PR 本文に明記
- [ ] **Phase 分割時の子 issue 起票**: 「Phase 2 は別途」等で残タスクを先送りする場合、子 issue 番号を親 issue に記載
- [ ] **CI 全通過**: `gh pr checks <PR>` で全 green
- [ ] **ruff / ruff format / pytest 全通過**

### Issue クローズルール

- PR マージ = 自動クローズではない (`Closes`, `Fixes` キーワード**禁止**)
- マージ後、PR 担当セッションが issue 本文の `- [ ]` を全チェックし、受け入れ条件を実測で満たしたことを確認してから `gh issue close`
- 残タスクが判明した場合は新 issue を起票し、親 issue に link してからクローズ

## タスク発見 (旧 /check-work の代替)

旧ロール前提の `/check-work` は廃止。新規タスクは以下の手順で発見する:

1. `gh issue list --state open --assignee Idios --sort updated` で最近更新された issue を確認
2. スコープラベル (`l2a-gui`, `l2b-installer`, `l2c-guard`, `l2-workflow`) でフィルタし、優先度 (`P1-high`) 順に並べる
3. 着手対象が選ばれたら `/plan` を呼んで実装前の計画を固める

ユーザーが「次に何する?」と聞いた場合、Claude は上記を実施し `AskUserQuestion` で候補提示する。

## 計画フェーズ (/plan skill の運用)

実装着手前の曖昧点洗い出しを標準化する。`/plan <issue番号>` 呼び出し時の出力:

1. **現状理解**: 対象 issue の本文を要約、依存 issue / 関連 PR の一覧
2. **リスクと曖昧点**: 実装時に発生しうる不確実性 (API 選定、互換性、パフォーマンス、外部依存等) をリスト化
3. **実装ステップ案**: タスクを 2-5 個のサブステップに分解
4. **判断ポイント**: ユーザーに確認すべき方針選択肢を `AskUserQuestion` で提示

ユーザーが方針承認後、`/implement` に移る。計画段階で未決事項が残る場合は plan mode を維持。

## Issue ラベル運用

`role:*` ラベルは**廃止**。代替として以下を使う:

### prefix ラベル (既存維持)

- `[bug]` — バグ修正
- `[doc]` — ドキュメント
- `[refactor]` — リファクタリング
- `[task]` — 通常タスク (enhancement 含む)
- `[question]` — 方針判断が必要
- `[risk]` — リスク顕在化

### スコープラベル (新設)

- `l2a-gui` — GUI 関連 (#105 系)
- `l2b-installer` — インストーラ関連 (#106 系)
- `l2c-guard` — guard 統合 (guard-integration.md §10)
- `l2-workflow` — 開発プロセス改善
- `l2-decision` — 方針決定 issue
- `l1-residual` — L1 残課題 (#412-#440 系)

### 優先度ラベル (既存維持)

- `P1-high` — 後続の前提条件
- `P2-medium` — 通常
- `P3-low` — 見直し時に再検討

## Memory 階層化

3 層構造で知見を管理する:

| 層 | 場所 | 寿命 | 内容 |
|---|---|---|---|
| L1 | `CLAUDE.md`, `MEMORY.md` | 恒久 | プロジェクト規約、skill 索引、ワークフロー要約 |
| L2 | `~/.claude/projects/<project>/memory/feedback_*.md` | 中期 | ユーザー指摘の蓄積、判断基準のチューニング |
| L3 | `docs/knowledge/*.md` | 恒久 (プロジェクト共有) | セッション横断の調査結果、トラブルシュート |

**L2 → L3 昇格**: feedback が複数セッションで再利用される汎用知見に育ったら `docs/knowledge/` へ移動し、memory からは削除。

## ユーザー確認ルール (bulk 操作 / 曖昧判断)

旧「独走パターン是正 (#399/#400)」を skill 横断の規約として継承:

- **bulk 操作** (3 件以上の issue 編集、ブランチ削除、ラベル一括変更等): 必ず `AskUserQuestion` で事前確認
- **曖昧判断**: 複数選択肢がある場合、ユーザーに選ばせる (Recommended 付き)
- **スコープ拡張**: 当初 issue の範囲外の変更が必要になったら、作業を止めて確認 or 別 issue 起票

## 移行前後の対応表

旧 → 新の変換:

| 旧ロール/command | 新 skill / 運用 |
|---|---|
| `/assume-role <role>` | 削除。ユーザーと Claude の 1 対 1 セッションのみ |
| `/setup-session <role> <N>` | 削除。worktree は main 統合後の claude 自動 worktree のみ |
| `/check-work` | skill 廃止。「## タスク発見」節の手順で代替 |
| director (戦略・方針) | ユーザー (Idios) 自身が判断。Claude は選択肢提示 |
| lead-engineer (設計・レビュー) | `/plan`, `/review-pr` skill |
| engineer (実装) | `/implement` skill |
| tester (テスト) | `/test-pr` skill |
| `role:director` ラベル | スコープラベル (`l2-workflow` 等) で代替 |
| `role:lead-engineer` ラベル | 同上 |
| `role:engineer` ラベル | 同上 |
| `role:tester` ラベル | 同上 |

## スキル間の引き継ぎ (旧ロールハンドオフの代替)

旧ワークフローでは PR 作成 → lead-engineer レビュー → tester テスト → director マージ の 4 ロール間でラベル付け替えが必要だった。新ワークフローでは**単一セッションが順次 skill を呼ぶ**ため、ハンドオフは不要:

```
/plan #N → 計画合意 → /implement #N → PR 作成 → /review-pr #PR → (修正あれば /implement 再実行) → /test-pr #PR → ユーザー承認 → マージ
```

各 skill の完了報告で次の skill に渡すコンテキストを明示する (PR 番号、テスト結果等)。

## 今後の追加 skill

L2 実装過程で必要と判明した場合のみ新設する。初期は上記 6 skill で凍結。候補:

- `/debug-brightness` (既存) — L1 時代の debug-brightness skill (保留)
- `/audit-recent-prs` — 月次 PR audit、#367 パターン A-D 検出の自動化 (必要なら追加)
- `/grill-me` — 計画フェーズでの事前課題洗い出し (`/plan` に統合予定)

## 参考

- [code.claude.com/docs/en/skills](https://code.claude.com/docs/en/skills) — skill 設計ガイド
- [code.claude.com/docs/en/best-practices](https://code.claude.com/docs/en/best-practices) — 単一セッション推奨
- `docs/release-strategy.md` — ブランチ戦略の詳細
- `docs/issue-policy.md` — Issue 起票ルール (role:* 節を削除済み)
- `plans/deffere-issue-l2-deffered-1-l1-issue-2-graceful-clover.md` — L2 移行計画全体
