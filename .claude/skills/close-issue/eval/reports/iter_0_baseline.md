# /close-issue Iter 0 baseline レポート

**実施日**: 2026-04-27
**対象 SKILL**: `.claude/skills/close-issue/SKILL.md`
**dispatch**: subagent (general-purpose / model: sonnet) × 3 並列 / `run_in_background: true`
**シナリオ**: A (中央値 1:1) / B (束ね PR) / C (Phase 分割)

---

## メトリクス比較表

| 指標 | Scenario A | Scenario B | Scenario C |
|---|---|---|---|
| 精度 | 8/8 (1.00) | 8/8 (1.00) | 8/8 (1.00) |
| [critical] 成功率 | 7/7 | 6/6 | 7/7 |
| tool_uses | 2 | 3 | 3 |
| 推論 step 数 | 7 | 7 | 7 |
| duration (subagent self-report) | 90s | 60s | 60s |
| duration (実測 ms) | 122,159 | 116,692 | 113,756 |
| 不明瞭点 件数 | 5 | 5 | 4 |
| 失敗パターン台帳 件数 | 2 | 3 | 3 |

**全シナリオ精度 1.00 / [critical] 全 ○**。受け入れ条件 (本シナリオではシミュレーション要件) のレベルでは合格だが、構造的欠陥候補が検出されており Iter 1 前の skill 改修が必要。

---

## 不明瞭点の集約と構造分類

### 構造的欠陥候補 (SKILL.md の節欠落 / 判定基準不在レベル、Iter 1 前に修正)

| # | 欠陥 | 出現シナリオ | Iter 1 前修正方針 |
|---|---|---|---|
| 1 | session-id 取得方法が未記載 (`pwd` 等のコマンド例なし)、issue 本文に `作成:` がない場合のフォールバックも未規定 | A / B / C (3 件で重複) | Step 1 末尾に session-id 取得手順 + 空欄時フォールバック明記 |
| 2 | `AskUserQuestion` のインターフェース・「返答なしに close しない」強制が未明示 | A | Step 7 冒頭に強制条項を追加 (Iron Law 4 + 5 引用) |
| 3 | CI green = 受け入れ条件 ○ の楽観的代替境界が不明確 | B | Step 5 に「CI green は補助根拠、静的検証は必須」明記 |
| 4 | PR コメント実体にアクセスできない場合の `/test-pr` 既実施記録確認ルートが未明示 | A | Step 5 動的検証部に「コメント取得不能時は AskUserQuestion でユーザー確認」明記 |
| 5 | 動的検証 vs 実測必要 の判定境界 (slow マーカー / GPU / 30 秒等) が曖昧 | B / C (2 件) | Step 5 に基準 (slow マーカー / 30 秒目安 / GPU-only / audio 統合) 明記 |
| 6 | 受け入れ条件外の追加変更 (CLAUDE.md 等) を close 判定からどう仕分けるかが暗黙的 | B / C (2 件) | Step 4 マッピング表説明に「受け入れ条件外 diff は close 判定の阻害要因にしない」明記 |
| 7 | PR 本文や issue 本文の参照先 PR/issue 番号が実在しない場合の対応ルートが未明示 | A (失敗パターン台帳) | Step 5b に「参照先存在確認 + 不在時は (B) 残タスク化」明記 |

### 詳細詰め不足レベル (deferred 候補、Iter 2 以降または別 issue 追跡)

- 残タスク (B) の `/create-task` 実行タイミング (close 前後の順序)
- Step 5b の「該当なし」を明示 vs スキップの選択ルール
- 束ね PR で「全 PR 共通テスト pass」が各 issue 受け入れ条件 ○ を意味するかの解釈
- CLAUDE.md 内 section 粒度 (§GPU モード vs §デバッグ) での分離の明文化

---

## 失敗パターン台帳 (subagent 検出、Iter 1 前修正反映候補)

| # | Pattern | Example | General Fix Rule | 反映先 |
|---|---|---|---|---|
| 1 | PR コメント実体アクセス不可を「実施済み」とみなして進む | 受け入れ条件 #5 で「PR 本文に `/test-pr` 実施と書いてあるから OK」と即 ○ 判定 | コメント取得不能時は AskUserQuestion でユーザー確認、独断で ○ にしない | 修正 4 |
| 2 | 参照先 PR/issue が実在しないのにチェック済みとみなす | `## 確認項目` の「#923 で対応」を信用して未チェック項目を消化済みと判断 | 参照先は `gh` で実在確認、実在しない場合は (B) 残タスク化 | 修正 7 |
| 3 | CI green = 受け入れ条件 ○ の楽観的代替 | Step 5 で実際の grep を実行せず「CI green だから ○」とする | CI green は補助根拠、静的検証は必須 | 修正 3 |
| 4 | session-id なし issue での close コメント省略 | 起票 session-id が issue に記載されていないとき close コメントから省略 | 起票 session-id 不明時は省略可、ただし実行 session-id は必ず含める | 修正 1 |
| 5 | 束ね PR の「共通テスト」pass で双方 close 正当化 | `pytest` 全 pass を「#905 も #906 も OK」の一括根拠とする | テスト pass は各 issue 受け入れ条件への対応テストが pass したことを issue 単位で確認 | 修正 6 |
| 6 | Phase 判定を `closedByPullRequestsReferences` のみで行い `timelineItems` を確認しない | 古い PR 紐付けの見落とし | Step 1 で両フィールドを必ず照合 (現状記述 OK、強調の追補のみ検討) | 既存記述で OK |
| 7 | 受け入れ条件外 diff (CLAUDE.md 等) を close 判定の阻害要因として扱う | PR #917 の CLAUDE.md +18 行を「受け入れ条件未達」と誤解 | Step 4 にて受け入れ条件 = 列挙項目のみ、それ以外の diff は補記欄 | 修正 6 |
| 8 | #917 マージ確認後に #918 を確認せずに close に進む | Phase 1 のみ検証、Phase 1.5 を見落として close | Step 3 で全 PR の MERGED 確認を全件ループ完了後に次 Step (現状記述 OK、強調の追補のみ検討) | 既存記述で OK |

---

## Iter 1 前の SKILL.md 修正対応表

| 修正 # | 対象節 | 内容 |
|---|---|---|
| 1 | Step 1 (issue 取得末尾) | session-id 取得手順 (`pwd` ベース) + 空欄時フォールバック |
| 2 | Step 7 冒頭 | `AskUserQuestion` 強制、明示的「はい」回答なしの close 禁止 (Iron Law 4 + 5 違反) |
| 3 | Step 5 静的検証部 | CI green は補助根拠扱い、静的検証必須、§C フォールバック適用条件 |
| 4 | Step 5 動的検証部 | `/test-pr` 既実施記録のアクセス可否ルート (PR/issue コメント取得 → AskUserQuestion) |
| 5 | Step 5 検証手段 | 動的検証 vs 実測必要 の判定基準 (slow マーカー / 30 秒 / GPU / audio) |
| 6 | Step 4 マッピング表説明 | 受け入れ条件外 diff の仕分け (補記欄、close 判定阻害要因にしない) |
| 7 | Step 5b 末尾 | 参照先 PR/issue の実在確認 + 不在時の (B) 残タスク化 |

---

## 次ステップ (Iter 1 前)

1. `.claude/skills/close-issue/SKILL.md` に修正 1-7 を反映 (本セッション内で実施)
2. **新規 subagent** を 3 並列 dispatch して Iter 1 再評価 (memory `feedback_skill_revision_empirical.md` の Red Flag「同じ subagent を使い回そう」回避)
3. Iter 1 で精度 1.00 維持 + 構造的欠陥候補 7 件すべて解消されているかを確認
4. 残った詳細詰め不足は deferred 候補として `summary.md` に記録、本 PR スコープ外
