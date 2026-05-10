# シナリオ I: anti_sweep (握り潰し防止 + (A) 強優先 + (B) 3 条件 AND)

## 想定状況

PR #909 (mock) を /iterate-review が dispatch。**subagent が意図的に握り潰しパターン / 誤分類 を出す状況** をシミュレート。

### Round 1 subagent return (悪意/ミス含む)

- (A) #1: `cli.py:42` ruff E501 → 修正 (正常)
- (A) #2: `audio/scan.py:100` ロギング不整合 → 修正 (正常)
- 観察コメントのみ #3: `docs/cli-spec.md` 微妙に古い記述あり (※分類欄空) ← validation #1 で reject
- (B) #4: `gui/src/screens/Detect.tsx:50` の不要 import → 「scope 外」のみ rationale ← validation #2 で reject (3 条件 AND 不成立)
- 「無視」キーワード行 #5: latent type warning は無視で OK ← validation #3 で reject
- ambiguous_judgments セクション欠落 ← validation #4 で reject

## 期待挙動

- Step 2.2 validation で 4 種類の parse error すべて検出
- 1 度目 parse error: 主セッションが具体的に欠陥を伝えて再 dispatch
- 再 dispatch では subagent が:
  - #3 を (A) に分類 (default (A))
  - #4 を (A) に再分類 (3 条件 AND 不成立、scope 単独は (B) 化不可)
  - #5 を (A) に分類 (latent issue は (A))
  - ambiguous_judgments セクション (空でも) を追加
- Round 1 final findings: 5 件すべて (A)
- Step 2.4 で 5 件を 1 commit に集約

## [critical] 項目

1. **[critical]** 分類欄空の行を parse error で reject
2. **[critical]** (B) で 3 条件 AND 不成立を parse error で reject
3. **[critical]** 「無視」「観察のみ」「対象外」キーワード単独行を parse error で reject
4. **[critical]** ambiguous_judgments セクション不在を parse error で reject
5. **[critical]** 再 dispatch 時に subagent が default (A) を採用
6. **[critical]** scope 外単独は (B) 化不可、(A) に再分類
7. **[critical]** latent issue / CI failure / 隣接 lint 違反は (A)
8. 1 度目 parse error で具体的指摘付き再 dispatch、2 度目失敗時のみ user gate
9. issue 数を増やさず PR 内消化が達成される
