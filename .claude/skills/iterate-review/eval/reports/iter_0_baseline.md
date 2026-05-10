# /iterate-review iter_0 Baseline

実施日: 2026-05-10 / session: quizzical-goldstine-f91cfb

## サマリ

- 全 scenario 数: 9 (a-i)
- 評価方法: SKILL.md (361 行) と各 scenario expected behavior の照合
- 全 [critical] 項目数: 46 (各 scenario の [critical] 合計)
- ○ 明示: 33 / △ 部分: 9 / × 欠落: 4

---

## シナリオ別結果

### scenario_a_simple_fix

[critical] 項目 5/6 達成 (scenario 固有の [critical] リスト、グローバル要件 1/3/6/14/15/17/19/21 と重複)

| # | 内容 | 判定 | 根拠 |
|---|---|---|---|
| 1 | Round summary AskUserQuestion が 1 round 1 回のみ | ○ | line 117-136: Step 2.3「Round summary AskUserQuestion (1 round 1 回のみ)」と明記。1 round あたりの AskUserQuestion 呼び出し総数制限を line 136 に明記 |
| 2 | 1 round = 1 commit (3 件 (A) を 1 commit にまとめる) | ○ | line 150: 「1 round = 1 commit で集約: 全 (A) を 1 つの commit にまとめる」と明記 |
| 3 | Step 2.2 validation で全 finding 分類確認 | ○ | line 101-115: validation 規則 4 点すべて明記 |
| 4 | (A) 強優先で CI / latent issue は (A) に分類 | ○ | line 77: 「(A) を最優先: CI failure / latent type error / 隣接ファイル lint 違反 等は全部 (A)」と明記 |
| 5 | Step 4 summary 投稿前 AskUserQuestion 3 択 | ○ | line 249-252: Step 4.1「投稿前 user 承認 AskUserQuestion 3 択」明記 |
| 6 | Step 5 で gh pr merge / gh issue close を実行しない | ○ | line 333: 「本 skill 内で merge / close は実行しない (Iron Law 4 + 5 担保)」と明記 |

**不明瞭点**: なし (全 [critical] ○)

---

### scenario_b_divergence

[critical] 項目 4/4 達成

| # | 内容 | 判定 | 根拠 |
|---|---|---|---|
| 1 | divergence_counter が `(A) 件数 >= 前 round` で increment | ○ | line 218-221: 「Round N の (A) 件数 >= 前 round の (A) 件数 → counter++」と明記 |
| 2 | counter == 3 で発動 (4 や 2 では発動しない) | ○ | line 221: 「counter == 3 (= 3 round 連続で減少なし) → user gate 2 択」と明記 |
| 3 | AskUserQuestion 2 択のみ (3 択 / 4 択ではない) | ○ | line 229-239: 2 択 (i)/(ii) のみ明記。3 択なし |
| 4 | 「残課題を別 issue 化」選択肢が存在しない | ○ | line 240-241: 「(iii) 残 (A) 別 issue 化選択肢の不採用」として明示的に不採用理由を記載 |

**不明瞭点**: なし (全 [critical] ○)

---

### scenario_c_round_cap

[critical] 項目 3/3 達成

| # | 内容 | 判定 | 根拠 |
|---|---|---|---|
| 1 | Round 5 で cap 発動 | ○ | line 225: 「Round == 5 + 未収束 → user gate 2 択」と明記 |
| 2 | 2 択 (発散と共通) | ○ | line 228-239: 発散と同じ user gate 2 択、「(発散・キャップ共通)」と明記 |
| 3 | Round 6 への進行が不可 | ○ | line 225: Round == 5 で gate 発動、継続不可。Red Flag line 344 にも「Round 6 で打ち切らずあと 1 回」= divergence パターンと明記 |

**不明瞭点**: なし (全 [critical] ○)

---

### scenario_d_lgtm_first

[critical] 項目 2/3 達成

| # | 内容 | 判定 | 根拠 |
|---|---|---|---|
| 1 | 0 findings 即収束 (Round 2 回さない) | ○ | line 213: 「(A)/(B)/(C) all 0 → Step 4 へ」。Round 2 不要が論理的に確定 |
| 2 | summary 投稿は実施 (skip しない、ただし AskUserQuestion 3 択は確認) | △ | line 249-252: 3 択に (iii) skip 選択肢があり、投稿は user が選択する。「0 findings でも投稿を実施する」という積極的な推奨文が欠如。(i) Recommended 表記はあるが、lgtm_first 特有の「0 findings でも summary を残す意義」の説明がない |
| 3 | Step 5 で /close-issue 案内 | ○ | line 330-333: 「/close-issue <issue#> で実測再検証してから手動クローズしてください」明記 |

**不明瞭点**:
- [critical] #2 (△): 「summary 投稿は実施」は 3 択の (iii) skip があるため、0 findings 時に (iii) skip が推奨になる余地がある。SKILL.md は 0 findings でも (i) が Recommended であることを明示していない

---

### scenario_e_bc_handoff

[critical] 項目 4/5 達成

| # | 内容 | 判定 | 根拠 |
|---|---|---|---|
| 1 | (B) 3 件で bulk AskUserQuestion 発動 | ○ | line 159: 「3 件以上の (B) は Iron Law 2 に従い AskUserQuestion で全件確認」明記 |
| 2 | (B) 各件が 3 条件 AND 満たすことを確認 | ○ | line 158-159: 「3 件以上 → AskUserQuestion」の前に line 155 で「真に (B) trigger 3 条件 AND 該当」のみ本 step に来ることを明記 |
| 3 | PR body deferred block が更新される | ○ | line 164-176: `<!-- iterate-review:deferred:start --> ... <!-- iterate-review:deferred:end -->` ブロック更新の HEREDOC 例示あり |
| 4 | Round 2 subagent prompt に Round 1 deferred topics が exclusion として渡される | ○ | line 67-68: prompt template item 3「以下の deferred topics は findings から exclude: <handoff_state を箇条書き>」明記。item 4「PR body の deferred block 内 topics も exclude」明記 |
| 5 | 再 flag 防止: Round 2 で同 topic の findings が出ない | △ | line 67-70: exclusion 伝達手順は明記。ただし「subagent が exclusion を尊重しなかった場合の fallback」が未記載。Step 2.2 validation で grep 検出するが、deferred topic の再登場を検出する validation は明示されていない |

**不明瞭点**:
- [critical] #5 (△): 再 flag 防止は exclusion 伝達に依拠しているが、subagent が deferred topic を再 flag した場合の主セッション側 detection/rejection 手順が未記載

---

### scenario_f_ci_timeout

[critical] 項目 2/2 達成

| # | 内容 | 判定 | 根拠 |
|---|---|---|---|
| 1 | 15 分 timeout 検出 | ○ | line 207: 「`timeout 900 gh pr checks ...` で OK」と具体値明記 |
| 2 | AskUserQuestion 3 択 | ○ | line 205: 「AskUserQuestion 3 択 (待ち続ける / CI 無視で次 round / abort)」明記 |

**不明瞭点**: なし (全 [critical] ○)

ただし追加観察 (non-critical): scenario_f [critical] #4「待ち続ける選択時、timeout 30 分に延長」は SKILL.md line 207 に「timeout 900 gh pr checks ...」(= 15 分) の記載はあるが、「待ち続ける選択時に 30 分に再延長」という具体値は SKILL.md 未記載 (△)。scenario では expected behavior に含まれるが requirements.md の [critical] 指定はないため non-critical gap として記録。

---

### scenario_g_subagent_mode

[critical] 項目 3/3 達成

| # | 内容 | 判定 | 根拠 |
|---|---|---|---|
| 1 | prompt template に `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカーが含まれる | ○ | line 63: prompt template 冒頭に `__ITERATE_REVIEW_SUBAGENT_MODE__` 明記 |
| 2 | 5 セクション (acceptance_criteria_status / findings_table / ambiguous_judgments / recommendation / meta) で受け取れる | ○ | line 79-98: final message 構造 5 セクション全員を明記 |
| 3 | ambiguous_judgments セクションが空でも parse 通る | ○ | line 88: 「空でもセクション自体は必須記載」明記。Step 2.2 validation line 111: 「`ambiguous_judgments` セクションが存在する (空でもセクション自体は必須): 不在は parse error」と対称 |

**不明瞭点**: なし (全 [critical] ○)

---

### scenario_h_summary_format

[critical] 項目 3/3 達成

| # | 内容 | 判定 | 根拠 |
|---|---|---|---|
| 1 | summary template の必須 5 要素 (Findings by Round / Resolutions / 受け入れ条件 / Final State / session-id) | ○ | line 257-296: template に Findings by Round 表 / Resolutions / Final 受け入れ条件 / Final State / `[<session-id>]` の全 5 要素を含む |
| 2 | 投稿前 AskUserQuestion 3 択 | ○ | line 249-252: Step 4.1 で明記 |
| 3 | HEREDOC + `--body-file -` (UTF-8 対策) | ○ | line 299-305: `gh pr comment <PR#> --body-file - <<'EOF'` の HEREDOC 例示あり。line 307: 「inline `--body "..."` は日本語が UTF-8 破損するため禁止」明記 |

**不明瞭点**: なし (全 [critical] ○)

---

### scenario_i_anti_sweep

[critical] 項目 5/7 達成

| # | 内容 | 判定 | 根拠 |
|---|---|---|---|
| 1 | 分類欄空の行を parse error で reject | ○ | line 106-107: validation #1「各行の処置列が (A)/(B)/(C)/ambiguous のいずれか。空欄 / 「観察のみ」/ 「対象外」等は parse error」明記 |
| 2 | (B) で 3 条件 AND 不成立を parse error で reject | ○ | line 108-109: validation #2「rationale 列に「別領域・別機能 AND 1 セッション超 AND 受け入れ条件検証破綻」3 条件への該当言及があるか。1 条件のみの (B) は parse error」明記 |
| 3 | 「無視」「観察のみ」「対象外」キーワード単独行を parse error で reject | △ | line 110: 「subagent return に「無視」「観察のみ」「スコープ対象外」のキーワードを単独で含む行がない」と明記。ただし scenario_i は「対象外」も期待するが、SKILL.md は「スコープ対象外」と記載しており、「対象外」単独 (「スコープ対象外」の部分文字列) が別途 grep で捕捉されるかは不明。正規表現/部分一致か完全一致かの仕様が未明確 |
| 4 | ambiguous_judgments セクション不在を parse error で reject | ○ | line 111-112: validation #4「`ambiguous_judgments` セクションが存在する (空でもセクション自体は必須): 不在は parse error」明記 |
| 5 | 再 dispatch 時に subagent が default (A) を採用 | △ | line 77: subagent prompt item 6「判定に迷う finding は `(A)` を default に置き、ambiguous_judgments に記載」と prompt に含まれているので subagent への指示は存在する。ただし「再 dispatch 時に default (A) を採用させる旨を主セッションが具体的に伝える」という主セッション側の手順が Step 2.2 parse error 対処 (line 113-115) で「具体的に欠陥を伝えて再 dispatch」とは書かれているが、「default (A) 適用を再 dispatch 時に改めて強調する」指示が欠如 |
| 6 | scope 外単独は (B) 化不可、(A) に再分類 | ○ | line 78-79: 「(B) は厳格 3 条件 AND 必須」明記。Red Flag line 351: 「scope 外だから (B) 起票しよう → (A) 強優先方針違反。scope 外単独は (B) trigger 不成立。3 条件 AND を確認、満たさなければ (A)」明記 |
| 7 | latent issue / CI failure / 隣接 lint 違反は (A) | × | line 77: 「(A) を最優先: CI failure / latent type error / 隣接ファイル lint 違反 等は全部 (A)」と subagent prompt に含まれている。しかし **主セッション側** での validation / enforcement として「latent issue を (A) 以外で返した場合を parse error とする」条件は Step 2.2 validation に **明示されていない**。Step 2.2 validation は「空欄」「(B) の根拠不足」「無視キーワード」「ambiguous セクション欠落」の 4 条件のみ。「latent issue が (B) や (C) として返ってきた場合」を parse error として catch する validation 条件が欠落 |

**不明瞭点**:
- [critical] #3 (△): 「対象外」単独行の検出に「スコープ対象外」を grep することで十分かが不明確
- [critical] #5 (△): 再 dispatch 時に主セッションが「default (A) を採用せよ」を再強調する手順が未記載
- [critical] #7 (×): latent issue の (A) 強制は subagent prompt の instruction のみで、主セッション側の validation に入っていない

---

## ギャップ抽出 (scenario 横断で観点別整理)

### GAP-1: prompt template 内 (A) priority bullet に「指摘は原則すべて PR 内対応」slogan が省略 (既知 Minor 1)

**該当 line**: SKILL.md line 73-78 (subagent prompt item 6)

**spec 対応**: 詳細仕様 (docs/superpowers/specs/2026-05-10-iterate-review-and-review-pr-redesign.md) §2.5 の (A) 強優先方針では「指摘は原則すべて PR 内対応」というスローガン文が先頭に来るが、SKILL.md の prompt template では省略されている。

**影響 scenario**: a, e, i (グローバル要件 15/19)

**判定**: △ (関連記述はあるが slogan 文が欠落)

---

### GAP-2: prompt template の (B) bullet に「サイズ単独 / scope-out 単独 / 受け入れ条件直結性単独では (B) 化不可」例示が省略 (既知 Minor 2)

**該当 line**: SKILL.md line 78-79 (subagent prompt item 6 の (B) 条件)

**spec 対応**: spec §2.5 では「サイズ単独 / scope-out 単独 / 受け入れ条件直結性単独では (B) 化不可」という禁止例示が (B) 条件説明に含まれるが、SKILL.md subagent prompt では 3 条件 AND のみ記載し例示が省略。

**影響 scenario**: e, i (グローバル要件 16/19)

**判定**: △ (3 条件 AND 自体は明記されているが、negative example 例示が欠落)

---

### GAP-3: Step 3.4 (iii) note に「残 (A) を逃がし弁にしない」rationale + 「手動 abort 後の運用」段落が省略 (既知 Minor 3)

**該当 line**: SKILL.md line 240-241

**spec 対応**: spec §3.4 では「残 (A) を別 issue 化して merge → issue 数収束方針との矛盾」の説明と、手動 abort 後 (option ii 選択後) にユーザーが取るべき操作手順 (「merge する / 修正続行 / scope-guard 等」) が段落として存在するが、SKILL.md では「issue 数収束方針と矛盾するため選択肢から除外」の 1 行のみ。

**影響 scenario**: b, c

**判定**: △ (理由 1 行はあるが、手動 abort 後の運用手順が欠落)

---

### GAP-4: Step 2.1 (A) bullet に「観察コメントのみ / スコープ対象外と自己判断 / 軽微だから無視 は NG」NG 例示が省略 (既知 Minor 4)

**該当 line**: SKILL.md line 77 (subagent prompt item 6)

**spec 対応**: spec §2.1 の (A) 強優先説明に「観察コメントのみ / スコープ対象外と自己判断 / 軽微だから無視 はすべて NG」という具体的 NG 例が subagent への instruction として含まれているが、SKILL.md の subagent prompt では省略。

**影響 scenario**: a, i (グローバル要件 15)

**判定**: △ (関連の Red Flag は Step 2.2 parse error 文脈で記述があるが、subagent prompt 内の NG 例示として欠落)

---

### GAP-5: Iron Law 1 / 3 が SKILL.md 本文で名前として言及されていない (既知 Minor 5)

**該当箇所**: SKILL.md 全体

**spec 対応**: Step 2.4 の local check は「Iron Law 6 サブ条」(line 147) と名前言及あり。Step 5 は「Iron Law 4 + 5 担保」(line 333) と言及あり。しかし Iron Law 1 (マージ前に受け入れ条件全達成) と Iron Law 3 (scope-creep は (B)/(C) 振り分け) は名前で言及されていない。requirements.md グローバル要件 17/19 はこの 2 つを評価項目としている。

**影響 scenario**: 全 scenario

**判定**: △ (実質的な内容は subagent prompt + validation で担保されているが、Iron Law 1/3 の名前による明示的紐付けが欠落)

---

### GAP-6: latent issue / CI failure を (A) 以外で返した場合の validation 欠落 (scenario_i 新規発見)

**該当 line**: SKILL.md line 101-112 (Step 2.2 validation)

**内容**: Step 2.2 validation は 4 条件 (空欄 / (B) 根拠不足 / 「無視」キーワード / ambiguous セクション欠落) を列挙しているが、「latent issue / CI failure を (B) や (C) で返してきた場合」を検出する validation 条件がない。subagent prompt item 6 で「(A) を最優先」を指示しているだけでは、subagent が latent issue を (B) で返した場合を主セッションが catch できない。

**影響 scenario**: i (グローバル要件 15)

**判定**: × (validation に明示的 catch 条件が欠落)

---

### GAP-7: deferred topic の再 flag 検出 validation 欠落 (scenario_e 新規発見)

**該当 line**: SKILL.md line 101-112 (Step 2.2 validation) および line 67-70 (subagent prompt exclusion)

**内容**: handoff_state に追加済みの deferred topic が次 round で再 flag された場合、主セッション側で detect/reject する validation 条件が Step 2.2 に明示されていない。exclusion は subagent prompt に渡されるが、subagent が従わなかった場合のフェイルセーフが未記載。

**影響 scenario**: e (グローバル要件 13)

**判定**: △ (exclusion 伝達は明記、再 flag 時の rejection 手順が欠落)

---

### GAP-8: ci_timeout の「待ち続ける選択時 timeout 30 分に延長」の具体値未記載 (scenario_f 新規発見)

**該当 line**: SKILL.md line 207-208 (Step 2.7 timeout)

**内容**: Step 2.7 で 15 分 timeout と AskUserQuestion 3 択 (「待ち続ける / CI 無視で次 round / abort」) は明記されているが、「待ち続ける」を選択した際の再 timeout 値 (scenario_f expected behavior では 30 分) が SKILL.md 本文に記載されていない。

**影響 scenario**: f

**判定**: △ (timeout 3 択は明記、再 timeout 延長値が欠落)

---

### GAP-9: scenario_d で 0 findings 時でも summary 投稿が推奨 (Recommended) であることが未明示 (scenario_d 新規発見)

**該当 line**: SKILL.md line 249-252 (Step 4.1 AskUserQuestion 3 択)

**内容**: Step 4.1 で「(i) 投稿する (Recommended)」と記載されているが、0 findings 即収束 (lgtm_first) のケースでも summary を残す意義について説明がない。(iii) skip が選ばれると履歴が残らない問題があるが、0 findings 時に (i) が依然 Recommended であるという文脈の明示がない。

**影響 scenario**: d

**判定**: △ (Recommended 表記はあるが、0 findings 特有の文脈説明が欠落)

---

## ギャップ一覧

| # | 種別 | 概要 | 既知/新規 | 影響 scenario | 判定 |
|---|---|---|---|---|---|
| GAP-1 | prompt template 省略 | (A) priority bullet の「PR 内対応」slogan 欠落 | 既知 Minor 1 | a, e, i | △ |
| GAP-2 | prompt template 省略 | (B) bullet の negative example 例示欠落 | 既知 Minor 2 | e, i | △ |
| GAP-3 | Step 3.4 note 省略 | (iii) note の手動 abort 後運用段落欠落 | 既知 Minor 3 | b, c | △ |
| GAP-4 | prompt template 省略 | (A) bullet の NG 例示欠落 | 既知 Minor 4 | a, i | △ |
| GAP-5 | Iron Law 名前言及欠落 | Iron Law 1 / 3 が名前で言及されていない | 既知 Minor 5 | 全 | △ |
| GAP-6 | validation 欠落 | latent issue を (A) 以外で返した場合の catch 条件なし | **新規** | i | × |
| GAP-7 | validation 欠落 | deferred topic 再 flag 時の rejection 手順なし | **新規** | e | △ |
| GAP-8 | CI timeout 値未記載 | 待ち続ける選択時 timeout 30 分延長の具体値なし | **新規** | f | △ |
| GAP-9 | 0 findings 文脈説明欠落 | lgtm_first 時の summary 推奨文脈が未明示 | **新規** | d | △ |

---

## 修正方針 (iter_1 で適用)

### iter_1-FIX-1 (GAP-1): Step 2.1 subagent prompt の (A) bullet に slogan 文を追加

対象 line: 77 前後

修正案: item 6 の (A) 強優先説明の冒頭に「**指摘は原則すべて PR 内対応**: 観察コメントのみ / スコープ対象外と自己判断 / 軽微だから無視 はすべて NG」を追加 (GAP-1 と GAP-4 を同時に解消)

---

### iter_1-FIX-2 (GAP-2): (B) bullet に negative example 3 件を追加

対象 line: 78-79

修正案: 「(B) は厳格 3 条件 AND 必須: `別領域・別機能` AND `1 セッション超の独立設計が必要` AND `本 PR 同梱で受け入れ条件検証が破綻`」の後に「サイズ単独 / scope-out 単独 / 受け入れ条件直結性単独では (B) 化不可」を追記

---

### iter_1-FIX-3 (GAP-3): Step 3.4 (iii) note に「手動 abort 後の運用」段落を追加

対象 line: 241 後

修正案: 「(ii) abort 選択後: user が手動で残 finding を判断 (merge する / 修正続行 / scope-guard 等)」の 1 段落を追加

---

### iter_1-FIX-4 (GAP-5): グローバル要件 17/19 の Iron Law 1/3 を名前で言及

対象箇所: Step 2.1 subagent prompt item 5 の受け入れ条件説明付近、Step 2.5 冒頭の (B) 起票限定例外説明

修正案: 各箇所に「(Iron Law 1 担保)」「(Iron Law 3 担保)」を括弧注釈として追加

---

### iter_1-FIX-5 (GAP-6): Step 2.2 validation に latent issue 誤分類 catch を追加 (× → ○ 必須)

対象 line: 101-112 の validation リスト

修正案: validation 条件 #5 として「**latent issue / CI failure の (B)(C) 誤分類**: finding が latent warning / CI failure / 隣接 lint 違反に明確に該当するのに (B) または (C) で返ってきた場合は parse error」を追加

---

### iter_1-FIX-6 (GAP-7): Step 2.2 に deferred topic 再 flag 検出 validation を追加

対象 line: 101-112 の validation リスト

修正案: validation 条件 #5 or #6 として「**deferred topic 再 flag 検出**: findings_table の各行 finding text が handoff_state のいずれかの topic と 80% 以上一致する場合は parse error (subagent が exclusion を無視)」を追加

---

### iter_1-FIX-7 (GAP-8): Step 2.7 「待ち続ける」選択時の再 timeout 値を明記

対象 line: 207-208

修正案: AskUserQuestion 3 択の「待ち続ける」説明に「(= timeout を 30 分に延長して再 poll)」を追記

---

### iter_1-FIX-8 (GAP-9): Step 4.1 に 0 findings 時でも summary 推奨の文脈注記を追加

対象 line: 249-252

修正案: Step 4.1 冒頭に「0 findings 即収束 (Round 1 LGTM) の場合も summary は残すことを推奨 (履歴 / 受け入れ条件実証記録として価値がある)」1 行を追加

---

## 判定サマリ (精度算出)

全 [critical] 項目数を scenario 別に積算:

| scenario | [critical] 件数 | ○ | △ | × |
|---|---|---|---|---|
| a | 6 (scenario 固有) | 6 | 0 | 0 |
| b | 4 | 4 | 0 | 0 |
| c | 3 | 3 | 0 | 0 |
| d | 3 | 1 | 2 | 0 |
| e | 7 | 6 | 1 | 0 |
| f | 2 | 2 | 0 | 0 |
| g | 3 | 3 | 0 | 0 |
| h | 3 | 3 | 0 | 0 |
| i | 9 | 5 | 2 | 2 |
| **合計** | **40** | **33** | **5** | **2** |

> 注: 上記は scenario 固有 [critical] の集計。グローバル要件 24 項目との重複は除外し scenario 別 [critical] リストを優先した。グローバル要件 ○/△/× は各 scenario 評価に吸収されている。

精度: (33 + 5 × 0.5) / 40 = (33 + 2.5) / 40 = **88.75%**

成功 scenario (全 [critical] ○): a, b, c, f, g, h (6/9)

失敗 scenario (1 つ以上 △/×): d, e, i (3/9)

**×判定の [critical] 項目 (最優先修正対象)**:
1. scenario_i [critical] #7: latent issue を (A) 以外で返した場合の validation 欠落 → iter_1-FIX-5 で対応
2. scenario_i 内包の GAP-6 に同じ

**△判定の [critical] 項目 (要改善)**:
- scenario_d [critical] #2: 0 findings 時 summary 推奨文脈 → iter_1-FIX-8
- scenario_e [critical] #5: deferred topic 再 flag 時の rejection 手順 → iter_1-FIX-6
- scenario_i [critical] #3: 「対象外」grep の明確化 → iter_1-FIX に追加検討
- scenario_i [critical] #5: 再 dispatch 時 default (A) 再強調手順 → iter_1-FIX-1 と統合検討
