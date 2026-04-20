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

## Red Flags (この思考が浮かんだら STOP)

| 浮かんだ思考 | 現実 |
|---|---|
| 「軽微だから勝手に直してよい」 | Iron Law 3 違反。別 issue に分ける |
| 「ついでにこれも修正しておこう」 | Iron Law 3 違反。スコープ外 |
| 「ユーザー確認は冗長だろう」 | Iron Law 2 / 5 違反。独走パターン #399 の再発 |
| 「受け入れ条件は大体満たしてる」 | Iron Law 1 違反。「大体」は NG。逐条検証必須 |
| 「Closes を付ければ自動で閉じて便利」 | Iron Law 4 違反。手動クローズ厳守 |
| 「観察 (修正不要) とコメントしておこう」 | #399 B 違反。別 issue 起票 or escalate |

詳細は `docs/l2-workflow.md` を参照。Iron Law が不明確な場合は先に l2-workflow.md を読むこと。
</EXTREMELY_IMPORTANT>
EOF
