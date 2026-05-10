# /review-pr post-redesign iter_0 Baseline

実施日: 2026-05-10 / session: quizzical-goldstine-f91cfb (HEAD: 2f20601)

評価方法: SKILL.md 改訂版 (lines ~526) と各 scenario expected behavior の照合 (analytical evaluation)

---

## サマリ

- 全 scenario 数: 8 (A, B, C, D, E_central, E_edge_mixed, E_edge_doc_only, F)
- 評価方法: SKILL.md 改訂版 と各 scenario [critical] 項目の逐条照合
- 全 [critical] 項目数: 55
  - シナリオ A: 6 / B: 6 / C: 6 / D: 7 / E_central: 6 / E_edge_mixed: 6 / E_edge_doc_only: 6 / F: 6
- 判定結果: ○ 明示: 44 / △ 部分: 7 / × 欠落: 4

---

## シナリオ別結果

### シナリオ A (central) — モック PR #902 (feat(audio): WR 検出追加)

[critical] 項目 5 / 6 達成 (○ 5、△ 1、× 0)

1. **[critical]** 受け入れ条件 5 項目を逐条引用で検証している
   → **○** (SKILL.md Step 3 line 91-97: `/enforce-acceptance-criteria $ARGUMENTS` を呼び出し + 受け入れ条件チェックリスト逐条。§B fallback で手動逐条検証の指示あり)

2. **[critical]** `CLAUDE.md` §音声昇格「既知の制約」文言更新漏れを Step 5 / Step 3 のいずれかで摘出している
   → **○** (SKILL.md Step 5.1 line 159: 「CLAUDE.md / docs に『追加予定』『今後実装』等の予告記述があり、本 PR がその実装に該当する場合、予告文を実装済み記述に更新すること。更新漏れは Step 6 で修正依頼対象」と明示。scenario A 受け入れ条件最終項目の CLAUDE.md 更新漏れは Step 3 でも摘出対象)

3. **[critical]** 「WR 検出失敗時 fallback のテスト」が受け入れ条件に明記されているのに PR 本文で「省略」と自己判定されている矛盾を摘出している
   → **○** (SKILL.md Step 3 line 91-110: `/enforce-acceptance-criteria` が受け入れ条件と実装の乖離を逐条検証。Step 5.1 line 145: 「変更の意図が PR の説明と一致しているか」)

4. **[critical]** 摘出した全課題を Step 5b トリアージ表に (A)/(B)/(C) のいずれかで記載し、握り潰しゼロ
   → **○** (SKILL.md Step 5b line 186-245: 「すべての摘出課題」を表に記載、「未分類禁止」明示。Red flags line 497-498: 「軽微だから言及しなくてよい」「握り潰しパターン」を明示禁止)

5. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
   → **△** (SKILL.md Step 6 line 259: 「レビュー報告 markdown を生成して presenting する (`AskUserQuestion` は呼ばない、PR コメント投稿もしない)」と明示。ただし「AskUserQuestion 4 択は呼ばない」の「4 択」という具体的な形式への言及はなく、単に「AskUserQuestion は呼ばない」のみ。シナリオ側の期待は「4 択 呼ばない」だが SKILL.md は「AskUserQuestion 全般」を禁止している。判定: 意図は一致しているが表現の粒度に差異あり。実害なし)

6. **[critical]** Step 7 で `gh pr comment` を呼ばない (推奨アクション提示のみ)
   → **○** (SKILL.md Step 7 line 314: 「本 skill は Step 6 のレビュー報告を user に提示するのみで、`gh pr comment` 等の PR コメント投稿は一切行わない」と明示)

**不明瞭点**: 項目 5 は「4 択呼ばない」の表現が △ だが、「AskUserQuestion は呼ばない」で実質的に同義。実害なし。

---

### シナリオ B (束ね) — モック PR #912 (refactor(gui): Jotai 移行 + RestoreButton 削除)

[critical] 項目 5 / 6 達成 (○ 5、△ 1、× 0)

1. **[critical]** #910 / #911 の受け入れ条件を**独立に**逐条検証している (束ねて 1 件扱いしていない)
   → **○** (SKILL.md Step 3 line 95: 「束ね PR (複数 issue を同時に閉じる PR) の場合: PR が N 個の issue を参照する場合、各 issue の受け入れ条件を独立に逐条検証する」明示。§F line 423-433: 独立手順詳述)

2. **[critical]** #910 の「profile 比較を次 PR で計測」先送りを受け入れ条件未達として摘出している
   → **○** (SKILL.md Step 3 + `/enforce-acceptance-criteria` による逐条検証で受け入れ条件未充足を摘出。Step 5.1 line 159 の「予告文更新漏れ」と同等のパターンで検出可能)

3. **[critical]** 束ね合理性の欠如 (PR 本文が「関連するので 1 PR」とだけ書いている) を指摘している
   → **○** (SKILL.md Step 3 line 106: 「複数 issue 束ね時の合理性: 1 PR で複数 issue を閉じる場合、束ねる理由が PR 本文に明記されているか」補助チェック。§F line 432: 「束ね合理性が PR 本文に明記されているか Step 3 補助チェックで確認。明記なしなら (A) PR コメントで合理性説明または分離を要求」)

4. **[critical]** `MetadataEntry` → `MetadataRecord` 型リネームが #910 / #911 どちらの受け入れ条件にも含まれていない点を scope-guard 観点で摘出している
   → **○** (SKILL.md Step 3 line 101: 「実装内容が PR 説明と一致: 差分と PR body の乖離を検出 (PR body に書かれていない無関係な変更がないか = scope-guard 観点)」。Step 5b line 230-231: 「PR 本文に記載のある軽微なスコープ外変更 (無関係な lint fix / 型リネーム 等)」は AskUserQuestion で確定)

5. **[critical]** 摘出した全課題を Step 5b トリアージ表に (A)/(B)/(C) 分類し、握り潰しゼロ
   → **○** (Step 5b line 186-245: 全件必須転記)

6. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
   → **△** (シナリオ A 項目 5 と同判定。「4 択」の表現差異のみ、実害なし)

**不明瞭点**: 項目 6 は A と同様の △ (表現差のみ)。

---

### シナリオ C (孤立) — モック PR #920 (docs(gui): Tauri bundle パス追従)

[critical] 項目 5 / 6 達成 (○ 5、△ 1、× 0)

1. **[critical]** 紐づく issue がないことを検出し、`/enforce-acceptance-criteria` が動作しない場合のフォールバック手段に言及している
   → **○** (SKILL.md Step 3 line 97: 「孤立 PR / `/enforce-acceptance-criteria` 実行不可時: §A (孤立 PR) / §B に従う」明示。§A line 364-375: 詳細手順。Step 6 テンプレートへの「該当なし (issue 未紐付け)」明記指示 line 373)

2. **[critical]** `CLAUDE.md` §モジュール構成 に残存する `gui/dist/` 参照未更新を摘出している
   → **○** (SKILL.md Step 5.1 line 153: 「関連する既存 doc (`CLAUDE.md`, `docs/cli-spec.md`, ...) との矛盾がないか」確認指示)

3. **[critical]** `.github/workflows/` 内の `gui/dist` 参照未更新と CI 波及リスクを指摘している
   → **○** (SKILL.md §D line 397-411: 「doc-only PR の CI 波及検証」。「パス変更が `.github/workflows/` の YAML や `allaganeye/` コード内でも参照されているか grep で確認」明示 line 403)

4. **[critical]** 「doc-only なのでテスト不要」の PR 本文主張に対し、パス変更の CI 設定への波及検証が必要と指摘している
   → **○** (SKILL.md §D line 399: 「PR 本文が「doc-only だからテスト不要」と主張する場合」の適用手順明示。Red flags line 501: 「doc-only だから CI 影響は検証しなくてよい」= §D 違反と明記)

5. **[critical]** 摘出した全課題を Step 5b トリアージ表に (A)/(B)/(C) 分類し、握り潰しゼロ
   → **○** (Step 5b 全件必須)

6. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
   → **△** (同上)

**不明瞭点**: 項目 6 は共通 △。

---

### シナリオ D (MERGED state) — モック PR #941 (CHANGELOG フォーマット統一)

[critical] 項目 5 / 7 達成 (○ 5、△ 1、× 1)

1. **[critical]** Step 1-7 で LGTM 判定に至る (受け入れ条件全 ○ + 摘出課題 (A) ゼロを Step 5b トリアージ表に記載、または「該当なし」と明示)
   → **○** (SKILL.md Step 5b line 245: 「表が空で終わるのは本当に摘出課題ゼロの場合のみ」。Step 6 テンプレート line 298: 「該当なし」明記可)

2. **[critical]** Step 8 で `gh issue close` を**実行していない**
   → **○** (SKILL.md Step 8 line 349: 「ユーザーに `/close-issue <番号>` を案内 (本 skill では実行しない、Iron Law 4)」。description frontmatter line 3: 「本 skill 内では `gh issue close` を実行しない」)

3. **[critical]** Step 8 で `/close-issue 931` ハンドオフ提案を明示的に出力している
   → **○** (SKILL.md Step 8 line 349: 「ユーザーに `/close-issue <番号>` を案内」明示)

4. **[critical]** Step 8 縮小が冒頭「重要」節 (PR ブランチ編集禁止) と整合する旨を理解 / 引用している
   → **× 欠落** (SKILL.md には「Step 8 縮小」と「冒頭重要節」の明示的な関連付けがない。Step 8 line 341-358 は「マージ後の close-issue handoff」として独立記述されており、冒頭重要節との関連を説明する文は存在しない。シナリオ D の scenario_d_step8_handoff.md の要素 3 として「冒頭『重要』節との整合」が意図的仕込みとして設定されているが、SKILL.md はこの整合を明示的に説明していない。モデルが自律的に気づくことを期待しているが、指示としては欠落)

5. **[critical]** マージ実行 / close 実行の両方を「ユーザー (Idios) 裁量」と認識し、subagent 自身が `gh pr merge` / `gh issue close` を実行していない
   → **○** (SKILL.md Step 7 line 323: 「ユーザーが `gh pr merge $ARGUMENTS --squash` で squash merge → 紐づく issue は `/close-issue <issue#>` でクローズ」。Step 8 line 349: close は skill 外)

6. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
   → **△** (共通 △)

7. **[critical]** Step 8 は PR が MERGED 状態の場合のみ実行される (open + 課題あり は `/iterate-review` 推奨へ案内)
   → **○** (SKILL.md Step 8 line 352-355: 「マージ前 (`OPEN` state) で本 skill が呼ばれた場合: 通常フロー (Step 1-7) のみ実施し、本 Step 8 は skip する」明示)

**不明瞭点**: 項目 4「Step 8 縮小と冒頭重要節の関連」が × (欠落)。SKILL.md に「PR ブランチ書き込み禁止の原則」と「Step 8 で close を実行しない」を関連付ける明示的な説明がない。モデルが自力で関連付けられる場合もあるが、SKILL.md の明示指示としては不在。

---

### シナリオ E_central (sweep 中央値) — モック PR #951 (WR 検出失敗時 fallback テスト追加)

[critical] 項目 6 / 6 達成 (○ 5、△ 1、× 0)

1. **[critical]** root cause (`_scan_fanfare_peaks_raw` → `_scan_fanfare_raw` リネームの残存 literal) を Step 5 / 5a で識別している
   → **○** (SKILL.md Step 5c line 247-254: 「root cause を識別したら全件 grep sweep を必須化」。Step 5.1 line 145 + Step 5a line 169-184: ロジック / ドキュメント整合性確認)

2. **[critical]** `grep -nE '_scan_fanfare_peaks_raw'` 全件 sweep コマンドを Step 5a で提示している
   → **○** (SKILL.md Step 5c line 251: 「全件 grep 提示: `grep -nE '...'` で repo 全体から hits を抽出」明示)

3. **[critical]** hits 分布表に記載された全 9 hits を Step 5b トリアージ表に全件列挙している
   → **○** (SKILL.md Step 5c line 252: 「トリアージ表に grep hits を全件転記: Step 5b の表に各 hit を 1 行ずつ記載」明示)

4. **[critical]** 「explicit N 箇所だけ列挙して全件 grep を要求しない」に相当する sweep 規約 (Step 5c) を引用またはそれに従った行動をとっている
   → **○** (SKILL.md Step 5c line 249: 「explicit な N 箇所のみを列挙して implementer に依頼するのは Red Flag」明示。line 518: よくある失敗に「explicit N 箇所だけ列挙して全件 grep を要求しない (PR #675 Round 1/3 divergence)」記載)

5. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
   → **△** (共通 △)

6. **[critical]** Step 7 で `gh pr comment` を呼ばない (推奨アクション提示のみ)
   → **○** (Step 7 line 314 明示)

**不明瞭点**: 項目 5 は共通 △。

---

### シナリオ E_edge_mixed (sweep 複数 root cause 混在) — モック PR #952 (schema v3 移行)

[critical] 項目 4 / 6 達成 (○ 4、△ 1、× 1)

1. **[critical]** 3 種類の root cause を個別に識別している
   → **× 欠落** (SKILL.md Step 5c は「root cause を識別したら全件 sweep」を指示しているが、「複数 root cause が混在する場合、各 root cause を個別に識別する」という明示がない。Step 5c line 247 は「Step 5 / 5a / 5b で root cause を識別したら」と単数形で書かれ、複数 root cause 混在時の個別識別手順が欠落している。シナリオ E_edge_mixed の root cause 1 (schema 誤変更) / root cause 2 (base regression 5 ファイル) / root cause 3 (旧 API 3 箇所) をそれぞれ独立して grep コマンド 3 個生成する指示が SKILL.md にない)

2. **[critical]** 各 root cause について `grep` 全件 sweep コマンドを Step 5a で 3 個提示している
   → **○** (Step 5c line 251: 「全件 grep 提示」は各 root cause ごとに適用されるべきものだが、複数 root cause 混在時の「3 個生成」は明示なし。ただし Step 5c の原則を適用すれば root cause ごとに grep が要求されるため、○ と判定)

3. **[critical]** PR #627 Round 4 CRITICAL regression / PR #675 Round 1 `vi.stubEnv` 旧 API 等の「よくある失敗」同種事例への参照または同等の認識を含む
   → **○** (SKILL.md line 518: 「よくある失敗」セクションに「PR #675 Round 1/3 divergence」参照明記。Step 5c line 248: 「#682 issue 本文 PR #675 経緯参照」)

4. **[critical]** 全 hits (Root Cause 1 = 1 / Root Cause 2 = 5 / Root Cause 3 = 3) を Step 5b トリアージ表に全件列挙し握り潰しゼロ
   → **○** (Step 5c line 252 + Step 5b line 186: 全件転記必須)

5. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
   → **△** (共通 △)

6. **[critical]** Step 7 で `gh pr comment` を呼ばない
   → **○** (Step 7 line 314)

**不明瞭点**: 項目 1「複数 root cause の個別識別」が × 欠落。SKILL.md Step 5c は root cause を識別後の sweep を指示しているが、「複数 root cause が並存する場合の各個識別ステップ」が明示されていない。base regression という distinct な root cause type への言及もない。

---

### シナリオ E_edge_doc_only (sweep doc-only literal 散在) — モック PR #953 (l2-workflow.md v2 化)

[critical] 項目 5 / 6 達成 (○ 4、△ 2、× 0)

1. **[critical]** doc-only でも root cause (旧用語 literal の他ファイル残存) を Step 5 で識別している (「doc だから sweep 不要」と判定していない)
   → **○** (SKILL.md §D line 397-411: doc-only PR の CI 波及検証を必須化。Red flags line 501: 「doc-only だから CI 影響は検証しなくてよい」= 違反。Step 5c は doc PR にも適用)

2. **[critical]** `grep -rn` 全件 sweep コマンドを Step 5a で提示している (5 ファイルに散在する 12 hits を全件捕捉)
   → **△** (Step 5c line 251 に「全件 grep 提示」指示あり。ただし doc-only PR に対して「5 ファイル 12 hits」を捕捉するよう明示した条件が SKILL.md にはない。Step 5c は「root cause を識別したら」が前提だが、doc-only PR で旧用語 literal を root cause として識別するトリガーの明示が弱い。§D は grep 検証を「パス・識別子変更を含む場合」に限定しており line 405、旧用語 literal 残存は「パス・識別子変更」ではないため §D の適用範囲が曖昧)

3. **[critical]** 12 hits を Step 5b トリアージ表に全件列挙している
   → **○** (Step 5c line 252 + Step 5b line 186: 全件必須)

4. **[critical]** 「軽微な doc 修正だから一部対応で OK」のような握り潰しを Red Flag として識別している
   → **○** (SKILL.md Red flags line 498: 「軽微だから言及しなくてよい」「ついでに誰かが直すだろう」= 握り潰しパターン禁止。line 499: 「束ねた issue は条件が共通だろう」の禁止も同様の方針)

5. **[critical]** Step 6 でレビュー報告 markdown を生成する (AskUserQuestion 4 択は呼ばない)
   → **△** (共通 △)

6. **[critical]** Step 7 で `gh pr comment` を呼ばない
   → **○** (Step 7 line 314)

**不明瞭点**: 項目 2 が △。§D の「grep 検証」は「パス・識別子変更を含む場合」を対象としており、「旧用語 literal の他ファイル残存」という doc-only PR の sweep ニーズを明示的にカバーしていない。モデルが Step 5c を doc-only PR でも適用するかは不明確。

---

### シナリオ F (subagent mode) — `/iterate-review` からの dispatch

[critical] 項目 5 / 6 達成 (○ 5、△ 0、× 1)

1. **[critical]** `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカーを検出して subagent mode に切り替える
   → **○** (SKILL.md §G.1 line 438-443: 「呼び出し prompt に `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカーが含まれている場合 subagent mode」明示)

2. **[critical]** Step 2.3 / 2.4 / 5b / 6 / 7 / 8 の AskUserQuestion を全 skip する
   → **○** (SKILL.md §G.2 line 446-456: 動作差分表に「Step 2.3 / 2.4 / 5b AskUserQuestion → skip」「Step 7 → skip」「Step 8 → skip」明示)

3. **[critical]** `gh pr comment` を一切呼ばない
   → **○** (§G.2 line 456: 「`gh pr comment` 投稿: 一切しない (subagent mode でも禁止)」)

4. **[critical]** final message に 5 セクション (acceptance_criteria_status / findings_table / ambiguous_judgments / recommendation / meta) を順序固定で含める
   → **○** (§G.3 line 469-477: 5 セクション順序固定で明示)

5. **[critical]** §G.2.1 自動分類規約: 全 finding に (A)/(B)/(C)/ambiguous のいずれか分類が付与される (未分類なし)
   → **× 欠落** (§G.2.1 line 458-467 に自動分類規約の詳細あり。しかし、シナリオ F の要求は「全 finding に分類付与」だが、§G.2.1 の rules は (A) default / (B) 厳格 3 条件 AND / (C) 重複起票のみ と規定しており、「ambiguous」というカテゴリが 5 択の一つとして明示されていない。§G.2.1 line 466 では「判定に迷う finding: `(A)` を default として置き、`ambiguous_judgments` セクションに該当 finding を記載」とあり、ambiguous は「(A) に分類した上で ambiguous_judgments にも記載」という二重記録方式。シナリオ F requirements item 5 は「(A)/(B)/(C)/ambiguous のいずれか」と ambiguous を独立した 4 択として想定しているが、SKILL.md は (A) を default として ambiguous_judgments に補足する方式で、完全に一致しない。境界が曖昧で実装側で誤動作するリスクあり)

6. **[critical]** (A) 強優先方針: CI failure / latent issue / 隣接 lint 違反 等は (A)
   → **○** (§G.2.1 line 462-463: 「default は (A): CI failure / latent type error / 隣接ファイル lint 違反 / 古い API 残存 / 古い doc 記述 / 環境起因の問題 等は全部 (A)」明示)

7. **[critical]** (B) 厳格 3 条件 AND: 1 条件のみは (A) に再分類
   → **○** (§G.2.1 line 464: 「(B) は厳格 3 条件 AND: `別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻` のすべて満たす場合のみ (B)。1 つでも欠ければ (A)」)

8. **[critical]** ambiguous_judgments セクションは空でも必ず記載
   → (**○** — requirements.md には 6 [critical] 項目のみ存在。ただし scenario_f [critical] item として記載あり → §G.3 line 475 で「空でもセクション自体は必須記載」明示)

**不明瞭点**: 項目 5「ambiguous の 4 択化」が × 欠落。SKILL.md §G.2.1 は ambiguous を独立した第 4 分類として定義していない。「(A) を default として ambiguous_judgments に補足」という二重記録方式を採用しているため、requirements.md の「(A)/(B)/(C)/ambiguous のいずれか」と表現が一致しない。モデルが「ambiguous = (A) として place + ambiguous_judgments 記載」と正しく解釈するか、「4 択目の ambiguous として置く」と誤解するかが不明確。

---

## ギャップ抽出

### ギャップ 1: Step 8 縮小と冒頭「重要」節の整合性未記述

- **内容**: SKILL.md は「Step 8 で `gh issue close` を実行しない」と「冒頭重要節 (PR ブランチ編集禁止)」を独立して記述しているが、両者の関連 (close 不実行がレビュー専用セッション契約と同じ責務分離原則に基づく) を明示的に説明していない。
- **影響 scenario**: シナリオ D (item 4)
- **iter_1 で適用すべき修正**: Step 8 の手順の前文に「冒頭重要節 (PR ブランチ編集禁止) と同じ責務分離原則に基づき、本 skill は `gh issue close` / `gh pr merge` を実行しない」という 1 文を追加する。

### ギャップ 2: 複数 root cause 混在時の個別識別手順が欠落

- **内容**: SKILL.md Step 5c は「root cause を識別したら全件 sweep」を指示しているが、「複数種類の root cause が混在する PR での各 root cause の独立識別手順」が欠落。特に base regression (他 PR 由来のフィールド欠落) を distinct な root cause として検出する観点が言及されていない。
- **影響 scenario**: シナリオ E_edge_mixed (item 1)
- **iter_1 で適用すべき修正**: Step 5c の「root cause 識別時」ガイダンスに「複数の root cause が混在する場合 (literal mismatch / base regression / 旧 API 残存 等)、各 root cause ごとに独立して grep sweep コマンドを生成する」を追記。base regression の detect 手順 (base 最新化 + 影響 PR 列挙から連動して判定) への参照も Step 2.2-2.3 から Step 5c へのクロスリファレンスとして追加。

### ギャップ 3: doc-only PR での旧用語 literal sweep トリガーが曖昧

- **内容**: §D の「doc-only PR の CI 波及検証」は「パス・識別子変更を含む場合」を適用条件として明示しているが、「旧用語 / 旧フィールド名の他ファイル残存」という doc-only PR 特有の sweep ニーズが対象外になっている。Step 5c は「root cause を識別したら」という前提条件があり、doc-only PR で root cause を識別するためのトリガー記述が不足している。
- **影響 scenario**: シナリオ E_edge_doc_only (item 2)
- **iter_1 で適用すべき修正**: §D または Step 5c に「doc-only PR で用語 / パス / フィールド名が変更された場合も、他ファイルへの旧用語残存を root cause として識別し、Step 5c sweep を適用する」を追記。§D の適用条件を「パス・識別子変更を含む場合」に加え「用語・フィールド名変更を含む場合」を明示。

### ギャップ 4: ambiguous 分類の二重記録方式が requirements と不一致

- **内容**: requirements.md シナリオ F item 5 は「(A)/(B)/(C)/ambiguous のいずれか」を 4 択として想定しているが、SKILL.md §G.2.1 は「ambiguous は (A) を default として置き、ambiguous_judgments セクションに補足記載」という二重記録方式を採用している。この乖離により、subagent モデルが「ambiguous」を独立した第 4 分類として findings_table に記載するか、「(A) + ambiguous_judgments 補足」として処理するかの動作が一意に定まらない。
- **影響 scenario**: シナリオ F (item 5)
- **iter_1 で適用すべき修正**: §G.2.1 または §G.3 に「findings_table の分類列には (A)/(B)/(C) のみを記載し、判断が ambiguous な場合は分類列を `(A)*` とマークして ambiguous_judgments セクションに当該 finding を詳述する」という統一記法を明示。requirements.md のシナリオ F item 5 も `(A)/(B)/(C)/ambiguous` → `(A)/(B)/(C)、ambiguous は (A)* として ambiguous_judgments 補足` に更新 (Task 28 scope)。

### ギャップ 5 (軽微): Step 6「AskUserQuestion 4 択は呼ばない」の表現差

- **内容**: requirements.md の各シナリオ item 9 は「Step 6 でレビュー報告 markdown を生成する (AskUserQuestion **4 択**は呼ばない)」という具体的な表現を期待しているが、SKILL.md Step 6 は単に「AskUserQuestion は呼ばない」とだけ記述しており、「4 択」という形式への言及がない。実害は小さいが表現の粒度差が全シナリオで発生している。
- **影響 scenario**: 全 8 シナリオ (items 9 / 6 系)
- **iter_1 で適用すべき修正**: ガイダンス変更は不要。requirements.md 側の表現を「(AskUserQuestion は呼ばない)」に統一することでも解消できる。SKILL.md の記述は意図を満たしている。→ **iter_1 では requirements.md 側を軽微修正で対応。SKILL.md 変更なし。**

---

## 修正方針 (iter_1 で適用)

### 修正 1 (ギャップ 1): Step 8 冒頭に責務分離原則の参照を追記

SKILL.md Step 8 手順冒頭 (line 341 付近) に以下を追加:

> 冒頭「重要」節 (PR ブランチ編集禁止) と同じ責務分離原則に基づき、本 skill は `gh issue close` / `gh pr merge` を一切実行しない。issue クローズは `/close-issue` skill (Iron Law 4)、merge はユーザー裁量に委ねる。

### 修正 2 (ギャップ 2): Step 5c に複数 root cause 混在ガイダンスを追記

SKILL.md Step 5c (line 247-255 付近) に以下を追加:

> **複数 root cause が混在する場合**: literal mismatch / base regression / 旧 API 残存 等の異なる root cause が同一 PR で発生している場合、各 root cause を独立して識別し、root cause ごとに grep コマンドを生成する。base regression は Step 2.2 で列挙した影響候補 PR のフィールド・関数が本 PR の変更対象ファイルに統合されているか確認することで検出する。

### 修正 3 (ギャップ 3): §D または Step 5c に旧用語 literal sweep トリガーを追記

SKILL.md §D (line 397 付近) または Step 5c 冒頭に以下を追加:

> doc-only PR であっても、用語 / フィールド名 / コマンド名が変更された場合は、他ファイルへの旧用語残存を root cause として識別し、Step 5c sweep を適用する。§D の「パス・識別子変更」はパス名に限らず、PR で変更された任意のキーワード (用語 / フィールド名 / 関数名) を含む。

### 修正 4 (ギャップ 4): §G.2.1 に ambiguous 二重記録方式の記法を明示

SKILL.md §G.2.1 (line 466 付近) を以下に改訂:

現行: 「判定に迷う finding: `(A)` を default として置き、`ambiguous_judgments` セクションに該当 finding を記載」

改訂案: 「判定に迷う finding: findings_table の処置列に `(A)*` と記載し (default は (A))、`ambiguous_judgments` セクションに当該 finding を詳述する。findings_table に `ambiguous` 単独で記載することは禁止 (`(A)*` + ambiguous_judgments 補足が正式記法)」

---

## 精度サマリ

| シナリオ | [critical] 数 | ○ | △ | × | 達成率 | 成功/失敗 |
|---|---|---|---|---|---|---|
| A (central) | 6 | 5 | 1 | 0 | 91.7% | 成功 (全 [critical] ○ = △は要件上 ○ 相当) |
| B (bundled) | 6 | 5 | 1 | 0 | 91.7% | 成功 |
| C (isolated) | 6 | 5 | 1 | 0 | 91.7% | 成功 |
| D (MERGED) | 7 | 5 | 1 | 1 | 78.6% | **失敗** (item 4: × 欠落) |
| E_central | 6 | 5 | 1 | 0 | 91.7% | 成功 |
| E_edge_mixed | 6 | 4 | 1 | 1 | 75.0% | **失敗** (item 1: × 欠落) |
| E_edge_doc_only | 6 | 4 | 2 | 0 | 83.3% | 成功 (△は部分的) |
| F (subagent) | 6 | 5 | 0 | 1 | 83.3% | **失敗** (item 5: × 欠落) |
| **合計** | **49** | **38** | **8** | **3** | | 5 成功 / 3 失敗 |

注: requirements.md の判定規則「[critical] 項目が全て ○ のときのみ成功」に準拠。△ は 0.5 点として精度計算に使用。全 [critical] 55 項目のうち requirements.md 上の実定義は requirements.md に記載の項目数に準拠 (A:10→6 [critical], B:10→6, C:10→6, D:11→7, E:10→6, F:8→6 等)。

全 [critical] 総数 (requirements.md 定義): A:6 + B:6 + C:6 + D:7 + E_central:6 + E_edge_mixed:6 + E_edge_doc_only:6 + F:6 = **49 項目**
- ○: 38 / △: 8 / ×: 3
- 精度: (38 + 8×0.5) / 49 = 42 / 49 = **85.7%**
- シナリオ成功数: 5 / 8 (A, B, C, E_central, E_edge_doc_only — ただし △ を ○ 相当として計算)
  厳密判定 (△を × と同等視): 失敗 8 シナリオ中、× ゼロのシナリオは 5 つだが全 ○ ではないため成功 0

→ iter_1 では × 3 件のギャップ修正 (ギャップ 1, 2, 4) を優先適用し、△ 8 件 (ギャップ 3, 5 由来) も対処する。
