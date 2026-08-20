# EPT レポート: #945 Phase 2 (/release Step 0a-2 + Self-Test Fable 欄)

シナリオ定義は [`../scenario_a_fable_overview_gate.md`](../scenario_a_fable_overview_gate.md)。
判定基準 (defect-class = 成果物が変わったもの) と帰属分類は
[`../../review-pr/eval/reports/iter_945_fable_firing_point.md`](../../review-pr/eval/reports/iter_945_fable_firing_point.md)
と同一。

---

## Iteration 0 (baseline / red 実証)

対象テキスト: `HEAD~1` の `.claude/skills/release/SKILL.md` (Step 0a-2 を含まない)。

| Scenario | 成否 | accuracy (raw) | tool_uses | duration | retries |
| --- | --- | --- | --- | --- | --- |
| R-1 | **x (失敗)** | **2/5** | 2 | 167.0s | 0 |

### red の中身 — 今回は accuracy が判別力を持った

**[critical] 要件 2 が `x`** で判定 = 失敗。executor は改修前テキストを読んで
「この遷移点 (Step 0a 完了直後、Step 0b 着手前) にレビュワー起動の規定は**見つからなかった**」と
正しく結論し、`Codex` / `allaganeye-fable-consult` の双方について非該当の根拠まで示した。
そのうえで要件 2 / 3 / 4 を「レビュー自体が発生しないので充足できない」と自己申告した。

> **#949 の EPT では accuracy が改修前でも満点になり判別力を持たなかった**
> ([[feedback_ept_checklist_leaks_the_answer]])。今回そうならなかったのは、
> 要件 2 が「**数値が記録に含まれる**」という、**その機構が存在しない限り生成できない出力**を
> 要求しているため。成果物の*性質*ではなく*機構の産物*を要求すると red が出る。
> **checklist 設計の再利用可能な知見。**

### 構造化 reflection (iteration 0)

**R-1 #1 — 帰属: 改修対象 (Phase 2 で解消)**

- Issue: Step 0a → Step 0b の遷移点にレビュワー起動規定が存在しない。executor は
  `CLAUDE.md` の Iron Law 6 Pre-flight Step 5 と fable-consult の推奨トリガー 3 点を
  横断参照したうえで「いずれにも該当しない」と結論した
- General Fix Rule: 評価用 checklist は対象文書に実在が確認できる機構のみを前提に設計する
  (executor 自身の指摘。**これは harness への指摘だが、裏を返せば
  「機構が無い」ことを checklist が正しく検出した**という意味でもある)

---

## Iteration 1

### Changes

`/release` Step 0a-2 の新設 + `.github/pull_request_template.md` の Fable 欄 +
`check-pr-checklist.test.js` の pin 更新と生 exit code テスト。

### 実行結果

| Scenario | 成否 | accuracy (raw) | tool_uses | duration | retries | 新規 unclear | うち defect-class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-1 | o | 5/5 | 2 | 63.3s | 0 | 2 | **1** |

**red からの反転**: `x (2/5)` → `o (5/5)`。executor は
`Agent(subagent_type=allaganeye-fable-consult)` を名指しで起動し、
`fable 俯瞰レビュー: 実施 (finding N 件 / 消化 M 件 / 残 K 件 → Track D PR 本文へ転記)` を
skill 逐語で出し、残 K 件の転記義務にも言及した。duration も 167.0s → 63.3s。

### 構造化 reflection (iteration 1)

**R-1 #2 — 帰属: 改修対象 (defect、iteration 2 で修正)**

- Issue: Step 0a-2 が渡すべき材料として挙げた 3 点のうち **2 点がその時点で存在しない**。
  リリース PR 本文は Step 3 で作られ、CHANGELOG の「対象バージョンセクション」も
  見出しリネームが Step 3。この時点では `## [Unreleased]` のまま
- **executor は代替物を自力で発明して渡していた** — 「コミット分析結果のサマリー草稿」を
  release notes の代わりに、`[Unreleased]` の中身を対象バージョンセクションの代わりに
- Cause: step の配置 (#945 が Step 0a 直後に固定) と、参照する成果物の確定タイミング
  (Step 3) の整合を取っていなかった
- General Fix Rule: あるステップが**後続ステップの成果物**を入力として要求する場合、
  その成果物が当該時点で実在するかを検証する。無いものを対象に書くと、
  実行者が代替物を発明して渡すことになり、渡す材料が実行者ごとに変わる

**R-1 #3 — 帰属: harness (対応不要)**: シナリオが CHANGELOG 未リネーム状態を明示しているが、
改修前テキストでは Step 0a→0b の判断に関与しない情報だった。iteration 1 以降は関与する。

### 次の修正 (= iteration 2)

対象を 2 点へ絞り、**その時点で実在するものだけ**を挙げる:

- `CHANGELOG.md` の `## [Unreleased]` セクションの内容
- Step 0a の受け入れゲート達成状況

あわせて **release notes を別途渡す必要がない**ことを明記した —
`extract_release_notes.py` が CHANGELOG の当該セクションを丸ごと抽出して Release 本文に
するので、**CHANGELOG を見ることが release notes を見ることと等しい**。

(収束判定: 0 consecutive clears / 打ち切りまで 2 round)

---

## Iteration 2

### Changes

上記の材料リスト修正のみ。

### 実行結果

(iteration 2 の subagent 結果を以下に記録)
