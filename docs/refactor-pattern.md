# 大規模 refactor の Phase 分割パターン

単一 PR で touched files > 30 file or diff > 1000 line になりそうな refactor を **Phase 分割**するためのガイド。AppError migration (#663→#689→#714/716/725/730/733→#745→#746) を実例として codify する。

## 1. 適用条件

以下のいずれかを満たす場合に Phase 分割を**検討**する:

- 単一 PR で `git diff --stat` の touched files > 30 file
- 単一 PR で `git diff --shortstat` の `+lines, -lines` 合計 > 1000 line
- consumer (caller) 数が多く、一度に乗り換えると base regression を全 site で検出することになる
- legacy fallback と新 API が long-lived に並存する必要がある

**例外**: 自動生成 file の bulk regenerate (codegen / formatter pass) は touched > 30 でも Phase 不要。

## 2. Phase 設計原則

| Phase | 内容 | green 維持 |
| --- | --- | --- |
| Phase 0 | 設計 spec + 影響範囲 inventory (consumer 件数 / call site list) | docs only |
| Phase 1 | data layer / 共通 helper / 型定義 (consumer 0 でも green) | 新 API 追加、旧 API 残存 |
| Phase 2+ | 個別 site migration (per-site が独立 reviewable) | 各 site が新 API へ乗り換え、旧 API は引き続き動作 |
| Phase Final | legacy fallback 撤去、stale docstring sweep | 旧 API 削除、参照ゼロ確認 |

各 Phase の切れ目で **「green / regression なし / consumer が選択的に乗り換え可能」** を満たす粒度を維持する。

## 3. Reference: AppError migration (実例)

| PR | Phase | 内容 |
| --- | --- | --- |
| #663 | Phase 0 (spec) | AppError 型定義 + 全 site inventory (80 site) |
| #689 | Phase 1 | AppError 型 + helper 追加、legacy fallback 残存 |
| #714 / #716 / #725 / #730 / #733 | Phase 2 (per-site migration) | 5 PR で個別 site の AppError 化を分担 |
| #745 | Phase 3 | `*Error / *ErrorHint` 並列構造を unified `*ErrorState` に集約 |
| #746 | Phase Final | legacy fallback 撤去 + stale docstring sweep |

各 PR は base sync + Pre-flight Step 0-4 を通り、独立 reviewable。Phase 1 完了後の commit 数 = 約 80 site の 0% migration、Phase 2 完了後 = 100% migration、Phase Final で legacy 削除という flow。

## 4. Phase 切れ目の判定基準

1 PR で**以下 3 条件すべてを満たす**粒度に分ける:

- **green**: 当該 PR をマージ後、CI が green (pyright / pytest / lint / build / cargo check)
- **regression なし**: 既存機能の振る舞いが変わらない (新 API が opt-in、旧 API が default 動作維持)
- **consumer が選択的に乗り換え可能**: per-site で乗り換えタイミングを選べる (一括強制ではない)

3 条件が **同時に満たせない**場合、その PR は範囲が広すぎる → さらに小さな Phase に分割する。

## 5. 関連 doc

- [`docs/superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md`](superpowers/specs/2026-05-08-l2-appError-migration-completion-design.md) — AppError migration 元 spec
- [`docs/l2-workflow.md`](l2-workflow.md) §subagent 起動規約 — Phase 単位 subagent dispatch
- [`docs/issue-policy.md`](issue-policy.md) §`deferred` ラベル運用 — Phase 分割で sub-issue を起票する場合のルール
