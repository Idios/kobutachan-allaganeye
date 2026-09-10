# シナリオ F: Subagent invocation mode (`/iterate-review` 連携)

参考事例: `/iterate-review` Round 1 の dispatch シミュレーション

## 紐づく issue (mock)

シナリオ A の #901 を流用 (音声昇格条件に WR 検出を追加)。

---

## モック PR (mock)

シナリオ A の #902 を流用 (feat(audio): WR 検出を音声昇格 (B) 条件として追加)。

---

## 入力

`/iterate-review` 主セッションが Agent tool で本 skill を subagent dispatch する prompt:

````text
__ITERATE_REVIEW_SUBAGENT_MODE__

PR #902 を review してください。`/review-pr` skill を invoke しますが、以下の特例を必ず適用してください:

1. Step 6 / Step 7 の AskUserQuestion / `gh pr comment` 投稿 を SKIP
2. Step 5b トリアージ表を markdown 表形式で final message に含める
3. 以下の deferred topics は findings から exclude:
   (なし)
4. PR body の `<!-- iterate-review:deferred:start --> ... <!-- iterate-review:deferred:end -->` ブロック内 topics も exclude
5. Step 3 の受け入れ条件逐条検証結果 (`/enforce-acceptance-criteria`) も final message に含める
6. (A) 強優先方針 + 握り潰し禁止 (G.2.1 規約 適用)
7. final message は以下の構造で return:
   ## acceptance_criteria_status / ## findings_table / ## ambiguous_judgments / ## recommendation / ## meta
````

---

## 期待 output

### G.1 Mode 検出

- prompt 内の `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカーを検出
- subagent mode に切り替え

### G.2 動作差分

- Step 2.3 / 2.4 の AskUserQuestion を **skip** (`gh pr view`/`gh pr list` での確認のみ実施)
- Step 5b の (A)/(B)/(C) 個別振り分け AskUserQuestion を **skip**、§G.2.1 規約に従って自動分類
- Step 6 報告を final message に markdown で含める (conversation 内 presenting でなく)
- Step 7 / Step 8 を **skip** (orchestrator 代行)
- `gh pr comment` 呼び出し **皆無**

### G.2.1 自動分類規約適用

- 全 finding に分類 (A) / (A)* / (B) / (C) のいずれかを付与 (なしは禁止。`(A)*` ambiguous は ambiguous_judgments 補足必須)
- (A) を default、`関数リネーム他箇所影響調査痕跡欠如` 等は (A) に分類
- (B) は 3 条件 AND を rationale 列で根拠示し
- 「無視」「観察のみ」「対象外」キーワードを含む行は出力しない

### G.3 戻り値構造

- 5 セクション順序固定: acceptance_criteria_status / findings_table / ambiguous_judgments / recommendation / meta
- `ambiguous_judgments` セクションは空でも必ず記載
- meta に mergeStateStatus / 並行 PR 状態 / CI 状態を含める

---

## 不明瞭点 (失敗時に記入)

(失敗した [critical] 項目を 1 行で記録)

---

## [critical] 項目

1. **[critical]** prompt 内の `__ITERATE_REVIEW_SUBAGENT_MODE__` マーカーを検出して subagent mode に切替できる
2. **[critical]** Step 2.3 / 2.4 / 5b / 6 / 7 / 8 の AskUserQuestion / `gh pr comment` を一切呼ばない
3. **[critical]** final message に 5 セクションが順序固定で含まれる
4. **[critical]** §G.2.1 規約に従い全 finding に分類が付与される (未分類なし)
5. **[critical]** (A) 強優先方針が反映され、scope-out 単独は (A)、3 条件 AND 満たすときのみ (B)
6. **[critical]** ambiguous_judgments セクションが空でも必ず記載される
7. Step 3 受け入れ条件逐条検証 (`/enforce-acceptance-criteria` 経由) は subagent mode でも実行される
8. deferred-list に含まれた topic は findings から除外される
