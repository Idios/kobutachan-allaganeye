# /create-task 要件チェックリスト (L-β β-2 改訂後 Iteration 0)

## 判定規則

- 成功/失敗: [critical] 項目が全て ○ のときのみ成功
- 精度: ○ = 1.0、× = 0、部分的 = 0.5

---

## シナリオ A (bug 起票、L-γ doc 参照経路の無関連)

モック: ユーザー指示「allaganeye detect が Windows cp932 path で fail する bug を起票」。

1. **[critical]** **A-1**: prefix `[bug]` を選択
2. **[critical]** **A-2**: タイトル 40 文字以内、scope label `l1-cli` を付与
3. **[critical]** **A-3**: 重複チェック (`gh issue list --search "cp932 path"` ...) を実行
4. **[critical]** **A-4**: 作成前に user に確認 (タイトル / labels / 重複結果 / 本文 / 3 択)
5. **[critical]** **A-5**: `printf | gh issue create --body-file -` で日本語破損を回避 (Iron Law 6 Bash tool 既知バグ)

---

## シナリオ B (patch release 関連 issue、Track 構造判定)

モック: ユーザー指示「security alert の Dependabot fast-uri を v0.3.1 で吸収する task を起票」。

1. **[critical]** **B-1**: 末尾の `## Patch release 関連の issue 起票` subsection を引いて Track 構造を判定
2. **[critical]** **B-2**: 「Track A (security / dependency)」と判定し、prefix `[task]` + scope `l2-workflow` (or `l2-ci`) を付与
3. **[critical]** **B-3**: issue 本文の冒頭に「Track A 候補」と明記し `/release` Step 0c 分類を容易にする
4. **[critical]** **B-4**: `docs/release-process.md` §Patch release の Track 構造 (#L-γ A2) への link を本文に含める

---

## シナリオ C (deferred 状態の issue 起票、release-blocker 撤回後の運用)

モック: ユーザー指示「L3 OCR 検討の task issue を起票、現バージョン scope 外として deferred 付与」。

1. **[critical]** **C-1**: prefix `[task]` を選択
2. **[critical]** **C-2**: `deferred` ラベル付与
3. **[critical]** **C-3**: `release-blocker` ラベルは付与しない (M8 撤回、2026-05-17 確定)
4. **[critical]** **C-4**: 本文に「次 release タイミングで `/release` Step 0c に再評価される」前提を明示 (or scope 外の reason 明記)
