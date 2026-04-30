#!/usr/bin/env bash
# Inject project Iron Laws at session start / clear / compact.
# Inspired by obra/superpowers pattern: prompt-weighted self-restraint.

cat <<'EOF'
<EXTREMELY_IMPORTANT>
このプロジェクト (kobutachan-allaganeye) には以下の Iron Law がある。
違反が「1% でも」疑われる状況では STOP して AskUserQuestion でユーザー確認すること。
合理化 ("軽微だから", "後で直す", "ついでに") は Red Flag として自覚し、必ず止まる。

## Iron Law (絶対禁止事項)

1. **NO PR MERGE WITHOUT ALL ACCEPTANCE CRITERIA CHECKED**
   - 元 issue の `## 受け入れ条件` 各項目を逐条引用し、対応する diff / test を逐条引用してからでないと LGTM 出さない (#367 対策)
   - `/review-pr` 実行時は `enforce-acceptance-criteria` skill を必ず呼ぶ

2. **NO BULK OPERATION WITHOUT AskUserQuestion CONFIRMATION**
   - 3 件以上の issue 編集・ラベル付替・ブランチ削除・マージ・クローズ等は必ず事前確認 (#399 C, #400)
   - サンプル 1 件提示 + 「全件 OK / 個別調整 / やめる」の 3 択で聞く

3. **NO SCOPE CREEP WITHOUT NEW ISSUE**
   - 着手 issue の範囲外の変更が必要になったら、実装を止めて新 issue 起票 or ユーザー確認
   - 「ついでに直した」「軽微な改善」は Red Flag。scope-guard skill の判断に従う

4. **NO Closes / Fixes / Resolves KEYWORDS**
   - PR 本文・コミットメッセージで issue 自動クローズキーワード禁止
   - マージ後に受け入れ条件を実測検証してから手動 `gh issue close`

5. **NO INDEPENDENT JUDGMENT ON AMBIGUOUS POINTS**
   - 曖昧と認識している判断点は独断で prescribe せず AskUserQuestion で多肢選択
   - 「Recommended 付き 2-4 択」が標準

6. **NO PR CREATION WITHOUT VERIFIED CHECKS**
   - PR 作成前に変更ファイル path に応じた自動チェック (Python: `ruff check .` / `ruff format --check .` / `pyright` / `pytest`、GUI: `npm run lint` / `typecheck` / `test` / `build` / `cargo check`) を全 pass させる。「軽微だから skip」「Python のみだから GUI 側不要」は Red Flag (失敗パターン A 再発)
   - ロジック変更 (`gpu_detector.py` / `audio/*.py` / `video/detector.py` / `gui/src-tauri/**` 等) を含む場合は、ユーザー (Idios) に実機検証 (GPU / audio / 長時間動画 / GUI Tauri 起動) を `AskUserQuestion` で依頼する。「mock テスト pass = 実機検証不要」は Red Flag (失敗パターン B 再発)
   - **PR 作成 Pre-flight (#659 で運用化)**: `git fetch origin <base>` → `git log HEAD..origin/<base>` で取り込み未済 commit を確認 → 当 PR の touched files と交差するなら `git merge origin/<base>` で取り込み + 自動チェック再実行 → `gh pr list --search "<元issue#>" --state all` で並行 worktree PR 重複確認。「コンフリクト出ないから OK」「最近 fetch したから OK」は Red Flag (失敗パターン C 再発、`feedback_pr_review_base_merge_regression.md` / `feedback_concurrent_worktree_pr_check.md` 参照)
   - PR 本文には machine-verified を `[x]` で、machine-unverifiable を plain bullet `-` で書き分ける (`feedback_pr_validate_checklist.md` 規約)。詳細手順は `feedback_pr_pre_creation_checks.md` / `feedback_user_realmachine_test_request.md` 参照

## Red Flags (この思考が浮かんだら STOP)

| 浮かんだ思考 | 現実 |
|---|---|
| 「軽微だから勝手に直してよい」 | Iron Law 3 違反。別 issue に分ける |
| 「ついでにこれも修正しておこう」 | Iron Law 3 違反。スコープ外 |
| 「ユーザー確認は冗長だろう」 | Iron Law 2 / 5 違反。独走パターン #399 の再発 |
| 「受け入れ条件は大体満たしてる」 | Iron Law 1 違反。「大体」は NG。逐条検証必須 |
| 「Closes を付ければ自動で閉じて便利」 | Iron Law 4 違反。手動クローズ厳守 |
| 「観察 (修正不要) とコメントしておこう」 | #399 B 違反。別 issue 起票 or escalate |
| 「ローカル lint 通ったから PR 出して大丈夫」 | Iron Law 6 違反。変更 path から必要 job を判定 (Python / GUI / installer / docs)。GUI 変更を含むなら `npm run lint` / `typecheck` / `test` / `build` / `cargo check` も実行 |
| 「mock テスト pass = 実機検証不要」 | Iron Law 6 違反。GPU / audio / 長時間動画 / GUI Tauri は mock 不可。該当 path 変更時は `AskUserQuestion` で依頼 |
| 「コンフリクト出ないから base 取り込み確認は不要」 | Iron Law 6 Pre-flight 違反。merge 可否と機能 regression は別軸。PR #627 Round 4 の失敗パターン C 再発 |
| 「並行 worktree PR は計画段階で確認したから PR 作成時は skip」 | Iron Law 6 Pre-flight 違反。計画後に別 worktree が PR 提出するケースあり (#646 / #647)。PR 作成時にも実施 |
| 「(A) PR 内修正は PR が大きくなるから別 issue にしよう」 | レビュー摘出問題は原則 (A) PR 内追加修正 (`feedback_pr_internal_fix_policy.md` 昇格)。サイズだけで (B) を選ばない |

詳細は `docs/l2-workflow.md` を参照。Iron Law が不明確な場合は先に l2-workflow.md を読むこと。
</EXTREMELY_IMPORTANT>
EOF
